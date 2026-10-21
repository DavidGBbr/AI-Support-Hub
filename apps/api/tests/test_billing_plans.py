import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.services import plans


def _settings(**overrides) -> Settings:
    base = {
        "postgres_host": "postgres",
        "postgres_user": "user",
        "postgres_password": "password",
        "postgres_db": "db",
        "redis_host": "redis",
    }
    base.update(overrides)
    return Settings(**base)


def test_catalog_exposes_the_free_and_the_pro_plan(stripe_env) -> None:
    catalog = {plan.code: plan for plan in plans.list_plans()}
    assert set(catalog) == {"free", "pro"}
    assert catalog["free"].stripe_price_id is None
    assert catalog["pro"].stripe_price_id == "price_test_pro"


def test_free_plan_allows_a_single_knowledge_base(stripe_env) -> None:
    assert plans.get_plan("free").max_knowledge_bases == 1
    assert plans.max_knowledge_bases("free") == 1


def test_pro_plan_allows_more_knowledge_bases(stripe_env) -> None:
    assert (
        plans.get_plan("pro").max_knowledge_bases
        > plans.get_plan("free").max_knowledge_bases
    )


def test_a_paid_status_grants_the_pro_plan(stripe_env) -> None:
    assert plans.resolve_plan_code("active", "price_test_pro") == "pro"
    assert plans.resolve_plan_code("trialing", "price_test_pro") == "pro"


def test_a_failed_payment_drops_the_workspace_back_to_free(stripe_env) -> None:
    assert plans.resolve_plan_code("past_due", "price_test_pro") == "free"
    assert plans.resolve_plan_code("unpaid", "price_test_pro") == "free"
    assert plans.resolve_plan_code("canceled", "price_test_pro") == "free"
    assert plans.resolve_plan_code("incomplete", "price_test_pro") == "free"


def test_past_due_can_keep_the_pro_plan_when_configured(
    monkeypatch, stripe_env
) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("PLAN_PRO_STATUSES", "active,trialing,past_due")
    get_settings.cache_clear()
    assert plans.resolve_plan_code("past_due", "price_test_pro") == "pro"


def test_another_price_never_grants_the_pro_plan(stripe_env) -> None:
    assert plans.resolve_plan_code("active", "price_of_another_product") == "free"


def test_the_legacy_price_variable_is_still_accepted(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_legacy")
    get_settings.cache_clear()
    assert get_settings().stripe_pro_price == "price_legacy"


def test_a_live_secret_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        _settings(stripe_secret_key="sk_live_should_never_work")


def test_a_live_publishable_key_is_refused() -> None:
    with pytest.raises(ValidationError):
        _settings(stripe_publishable_key="pk_live_should_never_work")


def test_an_empty_secret_key_is_accepted() -> None:
    assert _settings(stripe_secret_key="").stripe_secret_key == ""


def test_an_unknown_plan_is_reported(stripe_env) -> None:
    with pytest.raises(plans.UnknownPlan):
        plans.get_plan("enterprise")
