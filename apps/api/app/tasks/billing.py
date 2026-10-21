from app.core.celery import celery_app
from app.core.db import SessionLocal
from app.services import billing


@celery_app.task(name="apply_stripe_event")
def apply_stripe_event(event_id: str) -> dict[str, str]:
    """Apply a stored Stripe event to the subscription of its workspace."""
    with SessionLocal() as session:
        return billing.apply_stripe_event(session, event_id)
