from datetime import UTC, datetime
from typing import Any

import stripe
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.subscription import Subscription


class InvalidWebhookSignature(Exception):
    pass


class SubscriptionNotFound(Exception):
    pass


def _api_key() -> str:
    return get_settings().stripe_secret_key


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _as_dict(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def _latest_by_email(db: Session, email: str) -> Subscription | None:
    return (
        db.execute(
            select(Subscription)
            .where(Subscription.email == email)
            .order_by(Subscription.id.desc())
        )
        .scalars()
        .first()
    )


def _period_end_from_subscription(subscription: Any) -> datetime | None:
    timestamp = subscription.get("current_period_end")
    if timestamp is None:
        items = subscription.get("items", {}).get("data", [])
        if items:
            timestamp = items[0].get("current_period_end")
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _price_id_from_subscription(subscription: Any) -> str | None:
    items = subscription.get("items", {}).get("data", [])
    if not items:
        return None
    price = items[0].get("price") or {}
    return price.get("id")


def _upsert_from_subscription(db: Session, subscription: Any) -> Subscription:
    subscription = _as_dict(subscription)
    customer_id = subscription["customer"]
    row = db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer_id)
    ).scalar_one_or_none()
    if row is None:
        row = Subscription(stripe_customer_id=customer_id, status="incomplete")
        db.add(row)

    row.stripe_subscription_id = subscription.get("id")
    row.status = subscription.get("status", row.status)
    row.price_id = _price_id_from_subscription(subscription) or row.price_id
    row.current_period_end = _period_end_from_subscription(subscription)

    customer_email = subscription.get("customer_email")
    if customer_email:
        row.email = customer_email

    db.commit()
    db.refresh(row)
    return row


def _record_customer(db: Session, customer: Any) -> None:
    customer = _as_dict(customer)
    row = db.execute(
        select(Subscription).where(Subscription.stripe_customer_id == customer["id"])
    ).scalar_one_or_none()
    if row is None:
        row = Subscription(
            stripe_customer_id=customer["id"],
            email=customer.get("email"),
            status="incomplete",
        )
        db.add(row)
    elif customer.get("email"):
        row.email = customer["email"]
    db.commit()


def _get_or_create_customer(db: Session, email: str) -> str:
    row = _latest_by_email(db, email)
    if row is not None and row.stripe_customer_id:
        return row.stripe_customer_id

    customer = stripe.Customer.create(email=email, api_key=_api_key())
    _record_customer(db, customer)
    return customer["id"]


def create_checkout_session(db: Session, email: str) -> str:
    settings = get_settings()
    email = _normalize_email(email)
    customer_id = _get_or_create_customer(db, email)

    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url=f"{settings.web_base_url}/?checkout=success",
        cancel_url=f"{settings.web_base_url}/?checkout=cancel",
        api_key=_api_key(),
    )
    return checkout_session["url"]


def create_billing_portal_session(db: Session, email: str) -> str:
    settings = get_settings()
    email = _normalize_email(email)
    row = _latest_by_email(db, email)
    if row is None or not row.stripe_customer_id:
        raise SubscriptionNotFound(email)

    portal_session = stripe.billing_portal.Session.create(
        customer=row.stripe_customer_id,
        return_url=f"{settings.web_base_url}/",
        api_key=_api_key(),
    )
    return portal_session["url"]


def construct_event(payload: bytes, sig_header: str) -> Any:
    try:
        return stripe.Webhook.construct_event(
            payload, sig_header, get_settings().stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise InvalidWebhookSignature(str(exc)) from exc


def handle_event(db: Session, event: Any) -> None:
    event_type = event["type"]
    data = _as_dict(event["data"]["object"])

    if event_type == "checkout.session.completed":
        subscription_id = data.get("subscription")
        if subscription_id:
            subscription = stripe.Subscription.retrieve(
                subscription_id, api_key=_api_key()
            )
            _upsert_from_subscription(db, subscription)
        return

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        _upsert_from_subscription(db, data)
        return

    if event_type in {"invoice.paid", "invoice.payment_failed"}:
        subscription_id = data.get("subscription")
        if subscription_id:
            subscription = stripe.Subscription.retrieve(
                subscription_id, api_key=_api_key()
            )
            _upsert_from_subscription(db, subscription)
        return
