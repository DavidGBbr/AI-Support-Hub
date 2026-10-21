from dataclasses import dataclass

from app.core.config import get_settings


class UnknownPlan(Exception):
    pass


@dataclass(frozen=True)
class Plan:
    """Benefits granted by a subscription plan."""

    code: str
    name: str
    max_knowledge_bases: int
    stripe_price_id: str | None


def _build_plans() -> dict[str, Plan]:
    settings = get_settings()
    pro_price = settings.stripe_pro_price or None
    return {
        "free": Plan(
            code="free",
            name="Free",
            max_knowledge_bases=settings.plan_free_max_knowledge_bases,
            stripe_price_id=None,
        ),
        "pro": Plan(
            code="pro",
            name="Pro",
            max_knowledge_bases=settings.plan_pro_max_knowledge_bases,
            stripe_price_id=pro_price,
        ),
    }


def get_plan(code: str) -> Plan:
    plans = _build_plans()
    try:
        return plans[code]
    except KeyError as exc:
        raise UnknownPlan(code) from exc


def list_plans() -> list[Plan]:
    return list(_build_plans().values())


def plan_code_for_price(price_id: str | None) -> str | None:
    """Plan that owns a Stripe price, or None when the price is unknown."""
    if not price_id:
        return None
    for plan in _build_plans().values():
        if plan.stripe_price_id and plan.stripe_price_id == price_id:
            return plan.code
    return None


def resolve_plan_code(status: str, price_id: str | None = None) -> str:
    """Plan a subscription grants to its workspace.

    A workspace only reaches Pro with a status that counts as paid. When the
    price is known it must also be the Pro price, so an unrelated Stripe price
    never grants Pro access.
    """
    settings = get_settings()
    if status not in settings.plan_pro_status_set:
        return "free"
    pro_plan = get_plan("pro")
    if price_id and pro_plan.stripe_price_id and price_id != pro_plan.stripe_price_id:
        return "free"
    return "pro"


def max_knowledge_bases(plan_code: str) -> int:
    return get_plan(plan_code).max_knowledge_bases
