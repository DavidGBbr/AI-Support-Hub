import json
import time
from decimal import Decimal
from unittest.mock import patch

from stripe import WebhookSignature
from tests.conftest import (
    ADMIN_WORKSPACE,
    ADMIN_WORKSPACE_ID,
    OTHER_WORKSPACE_ID,
    WEBHOOK_SECRET,
)

from app.models.stripe_event import StripeEvent
from app.models.subscription import Subscription
from app.services import billing

BASE_TIME = 1_700_000_000


def _event(event_id: str, event_type: str, obj: dict, created: int = BASE_TIME) -> dict:
    return {
        "id": event_id,
        "object": "event",
        "api_version": "2024-06-20",
        "created": created,
        "livemode": False,
        "pending_webhooks": 1,
        "request": {"id": "req_1", "idempotency_key": None},
        "type": event_type,
        "data": {"object": obj},
    }


def _subscription(
    *,
    subscription_id: str = "sub_123",
    customer_id: str = "cus_123",
    status: str = "active",
    price_id: str = "price_test_pro",
    workspace_id: str = ADMIN_WORKSPACE_ID,
    cancel_at_period_end: bool = False,
) -> dict:
    return {
        "id": subscription_id,
        "object": "subscription",
        "customer": customer_id,
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "current_period_end": BASE_TIME + 2_592_000,
        "metadata": {"workspace_id": workspace_id},
        "items": {
            "data": [
                {
                    "price": {"id": price_id},
                    "current_period_end": BASE_TIME + 2_592_000,
                }
            ]
        },
    }


def _checkout_session(
    *,
    workspace_id: str = ADMIN_WORKSPACE_ID,
    customer_id: str = "cus_123",
    subscription_id: str = "sub_123",
) -> dict:
    return {
        "id": "cs_test_123",
        "object": "checkout.session",
        "customer": customer_id,
        "subscription": subscription_id,
        "client_reference_id": workspace_id,
        "metadata": {"workspace_id": workspace_id},
    }


def _post(
    billing_client, event: dict, *, secret: str = WEBHOOK_SECRET, sign: bool = True
):
    payload = json.dumps(event)
    headers = {"content-type": "application/json"}
    if sign:
        headers["stripe-signature"] = WebhookSignature.generate_signature_header(
            payload, secret, int(time.time())
        )
    return billing_client.post("/webhooks/stripe", content=payload, headers=headers)


def _drain(db_session, queued: list[str]) -> list[dict]:
    return [billing.apply_stripe_event(db_session, event_id) for event_id in queued]


def test_a_webhook_with_a_valid_signature_is_stored(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_1", "customer.subscription.updated", _subscription())
    response = _post(billing_client, event)
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert len(queued_events) == 1
    stored = db_session.get(StripeEvent, "evt_1")
    assert stored is not None
    assert stored.type == "customer.subscription.updated"
    assert stored.status == "received"


def test_a_webhook_with_an_invalid_signature_is_rejected(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_2", "customer.subscription.updated", _subscription())
    response = _post(billing_client, event, secret="whsec_another_secret")
    assert response.status_code == 400
    assert queued_events == []
    assert db_session.get(StripeEvent, "evt_2") is None


def test_a_webhook_without_a_signature_is_rejected(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_3", "customer.subscription.updated", _subscription())
    response = _post(billing_client, event, sign=False)
    assert response.status_code == 400
    assert queued_events == []
    assert db_session.get(StripeEvent, "evt_3") is None


def test_a_live_mode_event_is_rejected(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_4", "customer.subscription.updated", _subscription())
    event["livemode"] = True
    response = _post(billing_client, event)
    assert response.status_code == 400
    assert db_session.get(StripeEvent, "evt_4") is None


def test_a_payment_confirmed_moves_the_workspace_to_pro(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_paid", "customer.subscription.updated", _subscription())
    assert _post(billing_client, event).status_code == 200
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "active"
    assert row.plan_code == "pro"
    assert row.workspace_id is not None
    assert str(row.workspace_id) == ADMIN_WORKSPACE_ID
    assert row.stripe_subscription_id == "sub_123"
    assert row.stripe_customer_id == "cus_123"


def test_a_checkout_completion_moves_the_workspace_to_pro(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_checkout", "checkout.session.completed", _checkout_session())
    with patch(
        "stripe.Subscription.retrieve", return_value=_subscription()
    ) as retrieve:
        assert _post(billing_client, event).status_code == 200
        _drain(db_session, queued_events)
    assert retrieve.call_args.args[0] == "sub_123"

    row = db_session.query(Subscription).one()
    assert row.status == "active"
    assert row.plan_code == "pro"


def test_a_failed_payment_moves_the_workspace_back_to_free(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event("evt_ok", "customer.subscription.updated", _subscription()),
    )
    _drain(db_session, queued_events)

    _post(
        billing_client,
        _event(
            "evt_failed",
            "customer.subscription.updated",
            _subscription(status="past_due"),
            created=BASE_TIME + 10,
        ),
    )
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "past_due"
    assert row.plan_code == "free"


def test_an_invoice_payment_failure_moves_the_workspace_back_to_free(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event("evt_ok", "customer.subscription.updated", _subscription()),
    )
    _drain(db_session, queued_events)

    invoice = {
        "id": "in_1",
        "object": "invoice",
        "customer": "cus_123",
        "subscription": "sub_123",
    }
    with patch(
        "stripe.Subscription.retrieve",
        return_value=_subscription(status="past_due"),
    ):
        _post(
            billing_client,
            _event(
                "evt_invoice", "invoice.payment_failed", invoice, created=BASE_TIME + 10
            ),
        )
        _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "past_due"
    assert row.plan_code == "free"


def test_a_cancellation_moves_the_workspace_back_to_free(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event("evt_ok", "customer.subscription.updated", _subscription()),
    )
    _drain(db_session, queued_events)

    _post(
        billing_client,
        _event(
            "evt_canceled",
            "customer.subscription.deleted",
            _subscription(status="canceled"),
            created=BASE_TIME + 10,
        ),
    )
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "canceled"
    assert row.plan_code == "free"


def test_a_subscription_marked_to_cancel_keeps_the_pro_plan_until_the_end(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event("evt_ok", "customer.subscription.updated", _subscription()),
    )
    _drain(db_session, queued_events)

    _post(
        billing_client,
        _event(
            "evt_cancel_at_period_end",
            "customer.subscription.updated",
            _subscription(cancel_at_period_end=True),
            created=BASE_TIME + 10,
        ),
    )
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "active"
    assert row.plan_code == "pro"
    assert row.cancel_at_period_end is True


def test_a_canceled_subscription_is_not_revived(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event(
            "evt_canceled",
            "customer.subscription.deleted",
            _subscription(status="canceled"),
        ),
    )
    _drain(db_session, queued_events)

    _post(
        billing_client,
        _event(
            "evt_revive",
            "customer.subscription.updated",
            _subscription(status="active"),
            created=BASE_TIME + 10,
        ),
    )
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "canceled"
    assert row.plan_code == "free"


def test_an_out_of_order_event_does_not_change_the_state(
    billing_client, db_session, queued_events
) -> None:
    _post(
        billing_client,
        _event(
            "evt_new",
            "customer.subscription.updated",
            _subscription(status="active"),
            created=BASE_TIME + 100,
        ),
    )
    _drain(db_session, queued_events)

    _post(
        billing_client,
        _event(
            "evt_old",
            "customer.subscription.deleted",
            _subscription(status="canceled"),
            created=BASE_TIME,
        ),
    )
    outcomes = _drain(db_session, queued_events)

    assert outcomes[-1]["outcome"] == "ignored"
    row = db_session.query(Subscription).one()
    assert row.status == "active"
    assert row.plan_code == "pro"


def test_the_same_event_twice_does_not_duplicate(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_twice", "customer.subscription.updated", _subscription())
    assert _post(billing_client, event).status_code == 200
    assert _post(billing_client, event).status_code == 200
    _drain(db_session, queued_events)

    assert db_session.query(StripeEvent).count() == 1
    assert db_session.query(Subscription).count() == 1


def test_an_event_applied_twice_does_not_change_the_state(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_replay", "customer.subscription.updated", _subscription())
    _post(billing_client, event)
    _drain(db_session, queued_events)

    # Stripe redelivers an event the worker already processed.
    billing.apply_stripe_event(db_session, "evt_replay")
    row = db_session.query(Subscription).one()
    assert row.status == "active"
    assert row.plan_code == "pro"
    assert db_session.query(Subscription).count() == 1


def test_an_expired_checkout_marks_the_subscription_expired(
    billing_client, db_session, queued_events
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="free",
            status="incomplete",
            stripe_customer_id="cus_123",
        )
    )
    db_session.commit()

    event = _event(
        "evt_expired",
        "checkout.session.expired",
        {"id": "cs_test_123", "object": "checkout.session", "customer": "cus_123"},
    )
    _post(billing_client, event)
    _drain(db_session, queued_events)

    row = db_session.query(Subscription).one()
    assert row.status == "incomplete_expired"
    assert row.plan_code == "free"


def test_an_event_of_another_workspace_does_not_change_the_plan(
    billing_client, db_session, queued_events
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="pro",
            status="active",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
        )
    )
    db_session.commit()

    event = _event(
        "evt_other",
        "customer.subscription.updated",
        _subscription(
            subscription_id="sub_other",
            customer_id="cus_other",
            status="canceled",
            workspace_id=OTHER_WORKSPACE_ID,
        ),
    )
    _post(billing_client, event)
    _drain(db_session, queued_events)

    own = (
        db_session.query(Subscription)
        .filter(Subscription.workspace_id == ADMIN_WORKSPACE)
        .one()
    )
    assert own.status == "active"
    assert own.plan_code == "pro"


def test_an_unknown_event_type_is_stored_but_changes_nothing(
    billing_client, db_session, queued_events
) -> None:
    event = _event("evt_unknown", "customer.updated", {"id": "cus_123"})
    assert _post(billing_client, event).status_code == 200
    outcomes = _drain(db_session, queued_events)
    assert outcomes[-1]["outcome"] == "ignored"
    assert db_session.query(Subscription).count() == 0


def test_an_event_with_decimal_values_is_stored(
    billing_client, db_session, queued_events
) -> None:
    # Stripe decodes the decimal fields of an event back into Decimal, which
    # the database driver refuses to store as JSON.
    subscription = _subscription()
    subscription["items"]["data"][0]["unit_amount_decimal"] = "49.99"

    class _DecodedEvent:
        """What Stripe returns after decoding the raw payload."""

        def to_dict(self) -> dict:
            decoded = json.loads(json.dumps(subscription))
            decoded["items"]["data"][0]["unit_amount_decimal"] = Decimal("49.99")
            return {
                "id": "evt_decimal",
                "object": "event",
                "created": BASE_TIME,
                "livemode": False,
                "type": "customer.subscription.updated",
                "data": {"object": decoded},
            }

    event = _event("evt_decimal", "customer.subscription.updated", subscription)
    with patch("stripe.Webhook.construct_event", return_value=_DecodedEvent()):
        assert _post(billing_client, event).status_code == 200
    _drain(db_session, queued_events)

    stored = db_session.get(StripeEvent, "evt_decimal")
    assert stored is not None
    amount = stored.payload["data"]["object"]["items"]["data"][0]["unit_amount_decimal"]
    assert amount == 49.99
    row = db_session.query(Subscription).one()
    assert row.plan_code == "pro"


def test_a_row_written_by_another_worker_does_not_break_the_event(
    billing_client, db_session, queued_events, monkeypatch
) -> None:
    # Another worker wrote the row of the customer between the lookup and the
    # insert. The event still lands on that row instead of failing.
    _post(
        billing_client,
        _event("evt_first", "customer.subscription.updated", _subscription()),
    )
    _drain(db_session, queued_events)
    queued_events.clear()
    assert db_session.query(Subscription).count() == 1

    _post(
        billing_client,
        _event(
            "evt_second",
            "customer.subscription.updated",
            _subscription(status="past_due"),
            created=BASE_TIME + 10,
        ),
    )

    original = billing._find_subscription_row
    state = {"pending": True}

    def _lookup(db, **kwargs):
        # Only the lookup of the subscription row is hidden, and only once.
        if state["pending"] and kwargs.get("workspace_id") is not None:
            state["pending"] = False
            return None
        return original(db, **kwargs)

    monkeypatch.setattr(billing, "_find_subscription_row", _lookup)
    outcome = billing.apply_stripe_event(db_session, "evt_second")

    assert outcome["outcome"] == "applied"
    assert db_session.query(Subscription).count() == 1
    row = db_session.query(Subscription).one()
    assert row.status == "past_due"


def test_the_webhook_secret_is_not_written_to_the_logs(
    billing_client, db_session, queued_events, caplog
) -> None:
    event = _event("evt_log", "customer.subscription.updated", _subscription())
    with caplog.at_level("DEBUG"):
        _post(billing_client, event)
    assert WEBHOOK_SECRET not in caplog.text
