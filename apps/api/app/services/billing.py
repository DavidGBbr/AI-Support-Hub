from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.config import get_settings
from app.models.stripe_event import (
    EVENT_STATUS_FAILED,
    EVENT_STATUS_PROCESSED,
    EVENT_STATUS_RECEIVED,
    StripeEvent,
)
from app.models.subscription import Subscription
from app.services import plans

# Stripe events that change the subscription state of a workspace.
HANDLED_EVENT_TYPES = frozenset(
    {
        "checkout.session.completed",
        "checkout.session.expired",
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
    }
)


class InvalidWebhookSignature(Exception):
    pass


class SubscriptionNotFound(Exception):
    pass


class SubscriptionAlreadyActive(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class StripeNotConfigured(Exception):
    pass


def _api_key() -> str:
    return get_settings().stripe_secret_key


def _as_dict(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return dict(obj)
    return obj


def _json_safe(value: Any) -> Any:
    """Convert a Stripe payload into values that can be stored as JSON.

    Stripe decodes the decimal fields of an event back into Decimal objects,
    and the database driver refuses them. The payload is converted here, once,
    so the event is stored and replayed with the same values.
    """
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    return value


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize a datetime to UTC, tolerating naive values read from SQLite."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _event_created_at(event: Mapping) -> datetime:
    created = event.get("created")
    if isinstance(created, int | float):
        return datetime.fromtimestamp(created, tz=UTC)
    return datetime.now(UTC)


def _parse_uuid(raw: Any) -> UUID | None:
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _period_end_from_subscription(subscription: Mapping) -> datetime | None:
    timestamp = subscription.get("current_period_end")
    if timestamp is None:
        items = subscription.get("items") or {}
        data = items.get("data") or []
        if data:
            timestamp = data[0].get("current_period_end")
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _price_id_from_subscription(subscription: Mapping) -> str | None:
    items = subscription.get("items") or {}
    data = items.get("data") or []
    if not data:
        return None
    price = data[0].get("price") or {}
    return price.get("id")


def _subscription_id_from(data: Mapping) -> str | None:
    """Subscription id of an invoice or checkout session."""
    value = data.get("subscription")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return value.get("id")
    parent = data.get("parent") or {}
    details = parent.get("subscription_details") or {}
    value = details.get("subscription")
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return value.get("id")
    return None


def _find_subscription_row(
    db: Session,
    *,
    customer_id: str | None = None,
    subscription_id: str | None = None,
    workspace_id: UUID | None = None,
) -> Subscription | None:
    if subscription_id:
        row = db.execute(
            select(Subscription).where(
                Subscription.stripe_subscription_id == subscription_id
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    if workspace_id is not None:
        row = (
            db.execute(
                select(Subscription)
                .where(Subscription.workspace_id == workspace_id)
                .order_by(Subscription.created_at.desc())
            )
            .scalars()
            .first()
        )
        if row is not None:
            return row
    if customer_id:
        row = (
            db.execute(
                select(Subscription)
                .where(Subscription.stripe_customer_id == customer_id)
                .order_by(Subscription.created_at.desc())
            )
            .scalars()
            .first()
        )
        if row is not None:
            return row
    return None


# --------------------------------------------------------------------------- #
# Checkout
# --------------------------------------------------------------------------- #


def create_checkout_session(db: Session, *, workspace_id: UUID, email: str) -> str:
    """Create a Stripe Checkout session for the Pro plan of a workspace."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise StripeNotConfigured("STRIPE_SECRET_KEY is not configured")
    price_id = settings.stripe_pro_price
    if not price_id:
        raise StripeNotConfigured("STRIPE_PRO_PRICE_ID is not configured")

    existing = _find_subscription_row(db, workspace_id=workspace_id)
    if existing is not None and existing.status in {"active", "trialing"}:
        raise SubscriptionAlreadyActive(existing.status)

    metadata = {"workspace_id": str(workspace_id)}
    customer_id = existing.stripe_customer_id if existing is not None else None
    if customer_id:
        customer: dict[str, Any] = {"customer": customer_id}
    else:
        customer = {"customer_email": email.strip().lower()}

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=str(workspace_id),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        success_url=(
            f"{settings.web_base_url}/billing/success"
            "?session_id={CHECKOUT_SESSION_ID}"
        ),
        cancel_url=f"{settings.web_base_url}/billing/cancel",
        api_key=_api_key(),
        **customer,
    )
    return checkout_session["url"]


def create_billing_portal_session(db: Session, *, workspace_id: UUID) -> str:
    """Open the Stripe billing portal for the customer of a workspace."""
    settings = get_settings()
    row = _find_subscription_row(db, workspace_id=workspace_id)
    if row is None or not row.stripe_customer_id:
        raise SubscriptionNotFound(str(workspace_id))
    portal_session = stripe.billing_portal.Session.create(
        customer=row.stripe_customer_id,
        return_url=f"{settings.web_base_url}/billing",
        api_key=_api_key(),
    )
    return portal_session["url"]


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #


def construct_event(payload: bytes, sig_header: str) -> Mapping:
    """Validate the signature of a raw Stripe payload and return the event."""
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise InvalidWebhookSignature("stripe webhook secret is not configured")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise InvalidWebhookSignature(str(exc)) from exc
    if hasattr(event, "to_dict"):
        event = event.to_dict()
    event = _json_safe(event)
    if event.get("livemode"):
        raise InvalidWebhookSignature(
            "live mode events are rejected: this deployment is test mode only"
        )
    return event


def record_event(db: Session, event: Mapping) -> bool:
    """Store a verified event. Returns True when the event was not seen before."""
    event_id = str(event["id"])
    if db.get(StripeEvent, event_id) is not None:
        return False
    try:
        with db.begin_nested():
            db.add(
                StripeEvent(
                    event_id=event_id,
                    type=str(event.get("type", "")),
                    livemode=bool(event.get("livemode", False)),
                    event_created_at=_event_created_at(event),
                    status=EVENT_STATUS_RECEIVED,
                    payload=_json_safe(_as_dict(event)),
                )
            )
            db.flush()
    except IntegrityError:
        return False
    db.commit()
    return True


def event_needs_processing(db: Session, event_id: str) -> bool:
    row = db.get(StripeEvent, event_id)
    return row is not None and row.status != EVENT_STATUS_PROCESSED


def enqueue_event(event_id: str) -> None:
    """Hand the event over to the worker so the webhook answers fast."""
    from app.tasks.billing import apply_stripe_event

    apply_stripe_event.delay(event_id)


def apply_stripe_event(db: Session, event_id: str) -> dict[str, str]:
    """Apply a stored event to the subscription of its workspace.

    The stored event is locked for the duration of the work. Two workers that
    pick the same event therefore run one after the other, and the second one
    finds the event already processed.
    """
    row = db.execute(
        select(StripeEvent).where(StripeEvent.event_id == event_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return {"event_id": event_id, "outcome": "unknown_event"}
    if row.status == EVENT_STATUS_PROCESSED:
        db.rollback()
        return {"event_id": event_id, "outcome": "already_processed"}
    try:
        outcome = apply_event(db, row.payload)
    except Exception as exc:
        db.rollback()
        failed = db.get(StripeEvent, event_id)
        if failed is not None:
            failed.status = EVENT_STATUS_FAILED
            failed.error = str(exc)[:500]
            db.commit()
        raise
    row.status = EVENT_STATUS_PROCESSED
    row.processed_at = datetime.now(UTC)
    row.error = None
    db.commit()
    return {"event_id": event_id, "outcome": outcome}


def apply_event(db: Session, event: Mapping) -> str:
    """Update the subscription state from a verified Stripe event."""
    event_type = str(event.get("type", ""))
    if event_type not in HANDLED_EVENT_TYPES:
        return "ignored"
    data = _as_dict(event.get("data", {}).get("object", {}))
    event_created_at = _event_created_at(event)

    if event_type == "checkout.session.expired":
        return _handle_checkout_expired(db, data, event_created_at)

    stripe_subscription = _resolve_stripe_subscription(event_type, data)
    if not stripe_subscription:
        return "ignored"

    workspace_id = _resolve_workspace_id(db, data, stripe_subscription)
    applied = _apply_subscription(
        db, stripe_subscription, workspace_id, event_created_at
    )
    return "applied" if applied else "ignored"


def _resolve_stripe_subscription(event_type: str, data: Mapping) -> dict | None:
    if event_type.startswith("customer.subscription."):
        return _as_dict(data)
    subscription_id = _subscription_id_from(data)
    if not subscription_id:
        return None
    subscription = stripe.Subscription.retrieve(subscription_id, api_key=_api_key())
    return _as_dict(subscription)


def _resolve_workspace_id(
    db: Session, data: Mapping, stripe_subscription: Mapping
) -> UUID | None:
    """Find the workspace that owns the event."""
    for source in (data, stripe_subscription):
        metadata = source.get("metadata") or {}
        raw = metadata.get("workspace_id")
        if raw:
            parsed = _parse_uuid(raw)
            if parsed is not None:
                return parsed
    raw = data.get("client_reference_id")
    if raw:
        parsed = _parse_uuid(raw)
        if parsed is not None:
            return parsed
    row = _find_subscription_row(
        db,
        customer_id=stripe_subscription.get("customer"),
        subscription_id=stripe_subscription.get("id"),
    )
    return row.workspace_id if row is not None else None


def _apply_subscription(
    db: Session,
    stripe_subscription: Mapping,
    workspace_id: UUID | None,
    event_created_at: datetime,
) -> bool:
    """Write the Stripe subscription state. Returns True when it changed."""
    customer_id = stripe_subscription.get("customer")
    subscription_id = stripe_subscription.get("id")
    row = _find_subscription_row(
        db,
        customer_id=customer_id,
        subscription_id=subscription_id,
        workspace_id=workspace_id,
    )
    if row is None:
        row = _insert_subscription(
            db,
            customer_id=customer_id,
            subscription_id=subscription_id,
            workspace_id=workspace_id,
        )
        if row is None:
            # Another worker wrote the row first. Use the row it wrote.
            row = _find_subscription_row(
                db,
                customer_id=customer_id,
                subscription_id=subscription_id,
                workspace_id=workspace_id,
            )
            if row is None:
                return False

    last_event_at = _as_utc(row.last_event_at)
    if last_event_at is not None and event_created_at < last_event_at:
        # The event is older than the state we already have.
        return False
    same_subscription = row.stripe_subscription_id in (None, subscription_id)
    new_status = stripe_subscription.get("status")
    if same_subscription and row.status == "canceled" and new_status != "canceled":
        # A canceled subscription is never revived by a later event.
        return False

    status = str(stripe_subscription.get("status") or row.status)
    price_id = _price_id_from_subscription(stripe_subscription)
    row.status = status
    row.plan_code = plans.resolve_plan_code(status, price_id)
    row.cancel_at_period_end = bool(stripe_subscription.get("cancel_at_period_end"))
    row.current_period_end = _period_end_from_subscription(stripe_subscription)
    row.last_event_at = event_created_at
    if workspace_id is not None and row.workspace_id is None:
        row.workspace_id = workspace_id
    if customer_id and row.stripe_customer_id is None:
        row.stripe_customer_id = customer_id
    if subscription_id and row.stripe_subscription_id != subscription_id:
        row.stripe_subscription_id = subscription_id
    db.flush()
    return True


def _insert_subscription(
    db: Session,
    *,
    customer_id: str | None,
    subscription_id: str | None,
    workspace_id: UUID | None,
) -> Subscription | None:
    """Insert a subscription row.

    Returns None when another worker inserted the same customer first, so the
    caller can fall back to the row that is already there.
    """
    row = Subscription(
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
        workspace_id=workspace_id,
        plan_code="free",
        status="incomplete",
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        if object_session(row) is db:
            db.expunge(row)
        return None
    return row


def _handle_checkout_expired(
    db: Session, data: Mapping, event_created_at: datetime
) -> str:
    customer_id = data.get("customer")
    if not customer_id:
        return "ignored"
    row = db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    ).scalar_one_or_none()
    if row is None:
        return "ignored"
    last_event_at = _as_utc(row.last_event_at)
    if last_event_at is not None and event_created_at < last_event_at:
        return "ignored"
    if row.status != "incomplete":
        return "ignored"
    row.status = "incomplete_expired"
    row.plan_code = plans.resolve_plan_code(row.status)
    row.last_event_at = event_created_at
    db.flush()
    return "applied"


# --------------------------------------------------------------------------- #
# Read model
# --------------------------------------------------------------------------- #


def get_subscription_state(db: Session, *, workspace_id: UUID) -> dict[str, Any]:
    """State of the subscription of a workspace, without Stripe identifiers."""
    row = _find_subscription_row(db, workspace_id=workspace_id)
    plan_code = row.plan_code if row is not None else "free"
    plan = plans.get_plan(plan_code)
    current_period_end = _as_utc(row.current_period_end) if row is not None else None
    return {
        "plan_code": plan_code,
        "plan_name": plan.name,
        "status": row.status if row is not None else "incomplete",
        "max_knowledge_bases": plan.max_knowledge_bases,
        "cancel_at_period_end": row.cancel_at_period_end if row is not None else False,
        "current_period_end": (
            current_period_end.isoformat() if current_period_end is not None else None
        ),
    }
