from unittest.mock import patch

import pytest
from tests.conftest import (
    ADMIN_TOKEN,
    ADMIN_WORKSPACE,
    ADMIN_WORKSPACE_ID,
    AUTH_HEADERS,
    OTHER_WORKSPACE_ID,
    STRIPE_SECRET_KEY,
)

from app.core.config import get_settings
from app.models.subscription import Subscription

CHECKOUT_URL = "https://checkout.stripe.com/c/pay/cs_test_123"
PORTAL_URL = "https://billing.stripe.com/p/session/test"


def test_the_plan_catalog_is_public(billing_client) -> None:
    response = billing_client.get("/v1/plans")
    assert response.status_code == 200
    items = {item["code"]: item for item in response.json()["items"]}
    assert set(items) == {"free", "pro"}
    assert items["free"]["max_knowledge_bases"] == 1
    assert items["pro"]["max_knowledge_bases"] == 5


def test_checkout_without_authentication_is_refused(billing_client) -> None:
    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
    )
    assert response.status_code == 401


def test_checkout_with_a_wrong_token_is_refused(billing_client) -> None:
    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_checkout_of_another_workspace_is_not_found(billing_client) -> None:
    response = billing_client.post(
        f"/v1/workspaces/{OTHER_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_checkout_answers_503_when_billing_is_not_configured(
    billing_client, monkeypatch
) -> None:
    # An empty value, instead of a missing one, so the local .env file does
    # not bring the token back.
    monkeypatch.setenv("BILLING_ADMIN_TOKEN", "")
    monkeypatch.setenv("BILLING_ADMIN_WORKSPACE_ID", "")
    get_settings.cache_clear()
    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 503


def test_checkout_creates_a_stripe_session_for_the_pro_price(billing_client) -> None:
    with patch(
        "stripe.checkout.Session.create", return_value={"url": CHECKOUT_URL}
    ) as create:
        response = billing_client.post(
            f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
            json={"email": "Owner@Example.com"},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 200
    assert response.json() == {"url": CHECKOUT_URL}

    kwargs = create.call_args.kwargs
    assert kwargs["mode"] == "subscription"
    assert kwargs["line_items"] == [{"price": "price_test_pro", "quantity": 1}]
    assert kwargs["customer_email"] == "owner@example.com"
    assert kwargs["client_reference_id"] == ADMIN_WORKSPACE_ID
    assert kwargs["metadata"] == {"workspace_id": ADMIN_WORKSPACE_ID}
    assert kwargs["subscription_data"] == {
        "metadata": {"workspace_id": ADMIN_WORKSPACE_ID}
    }
    assert kwargs["success_url"].endswith("session_id={CHECKOUT_SESSION_ID}")
    assert kwargs["cancel_url"].endswith("/billing/cancel")


def test_checkout_reuses_the_customer_of_the_workspace(
    billing_client, db_session
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="free",
            status="canceled",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_old",
        )
    )
    db_session.commit()

    with patch(
        "stripe.checkout.Session.create", return_value={"url": CHECKOUT_URL}
    ) as create:
        response = billing_client.post(
            f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
            json={"email": "owner@example.com"},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 200
    assert create.call_args.kwargs["customer"] == "cus_existing"


def test_checkout_refuses_a_second_active_subscription(
    billing_client, db_session
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="pro",
            status="active",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_active",
        )
    )
    db_session.commit()

    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 409


def test_a_stripe_failure_is_reported_as_a_bad_gateway(billing_client) -> None:
    import stripe

    with patch(
        "stripe.checkout.Session.create",
        side_effect=stripe.InvalidRequestError("price is not allowed", "price_1"),
    ):
        response = billing_client.post(
            f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
            json={"email": "owner@example.com"},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 502
    assert "price is not allowed" not in response.text


def test_checkout_without_a_price_is_reported_as_unavailable(
    billing_client, monkeypatch
) -> None:
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_PRICE_ID", "")
    get_settings.cache_clear()
    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
        json={"email": "owner@example.com"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 503


def test_the_portal_needs_a_subscription(billing_client) -> None:
    response = billing_client.post(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/portal",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_the_portal_uses_the_customer_of_the_workspace(
    billing_client, db_session
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="pro",
            status="active",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_active",
        )
    )
    db_session.commit()

    with patch(
        "stripe.billing_portal.Session.create", return_value={"url": PORTAL_URL}
    ) as create:
        response = billing_client.post(
            f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/portal",
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 200
    assert response.json() == {"url": PORTAL_URL}
    assert create.call_args.kwargs["customer"] == "cus_existing"


def test_the_portal_of_another_workspace_is_not_found(billing_client) -> None:
    response = billing_client.post(
        f"/v1/workspaces/{OTHER_WORKSPACE_ID}/billing/portal",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_the_subscription_state_defaults_to_the_free_plan(billing_client) -> None:
    response = billing_client.get(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/subscription",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_code"] == "free"
    assert body["status"] == "incomplete"
    assert body["max_knowledge_bases"] == 1


def test_the_subscription_state_reads_the_persisted_plan(
    billing_client, db_session
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="pro",
            status="active",
            stripe_customer_id="cus_existing",
            stripe_subscription_id="sub_active",
        )
    )
    db_session.commit()

    response = billing_client.get(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/subscription",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["plan_code"] == "pro"
    assert body["max_knowledge_bases"] == 5


def test_the_subscription_state_never_exposes_a_stripe_identifier(
    billing_client, db_session
) -> None:
    db_session.add(
        Subscription(
            workspace_id=ADMIN_WORKSPACE,
            plan_code="pro",
            status="active",
            stripe_customer_id="cus_secret",
            stripe_subscription_id="sub_secret",
        )
    )
    db_session.commit()

    response = billing_client.get(
        f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/subscription",
        headers=AUTH_HEADERS,
    )
    assert "cus_secret" not in response.text
    assert "sub_secret" not in response.text


def test_the_subscription_state_of_another_workspace_is_not_found(
    billing_client,
) -> None:
    response = billing_client.get(
        f"/v1/workspaces/{OTHER_WORKSPACE_ID}/billing/subscription",
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_the_secret_key_is_not_written_to_the_logs(billing_client, caplog) -> None:
    with patch("stripe.checkout.Session.create", return_value={"url": CHECKOUT_URL}):
        with caplog.at_level("DEBUG"):
            billing_client.post(
                f"/v1/workspaces/{ADMIN_WORKSPACE_ID}/billing/checkout",
                json={"email": "owner@example.com"},
                headers=AUTH_HEADERS,
            )
    assert STRIPE_SECRET_KEY not in caplog.text
    assert ADMIN_TOKEN not in caplog.text


@pytest.mark.parametrize(
    "path",
    [
        "/v1/workspaces/{workspace}/billing/checkout",
        "/v1/workspaces/{workspace}/billing/portal",
        "/v1/workspaces/{workspace}/billing/subscription",
    ],
)
def test_every_billing_route_asks_for_credentials(billing_client, path) -> None:
    response = billing_client.get(path.format(workspace=ADMIN_WORKSPACE_ID))
    assert response.status_code in (401, 405)
