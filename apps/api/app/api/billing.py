from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.services import billing

router = APIRouter(prefix="/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbSession = Annotated[Session, Depends(get_session)]


class CheckoutRequest(BaseModel):
    email: str


class CheckoutResponse(BaseModel):
    url: str


class PortalRequest(BaseModel):
    email: str


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(body: CheckoutRequest, db: DbSession) -> CheckoutResponse:
    url = billing.create_checkout_session(db, body.email)
    if not url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe did not return a checkout URL",
        )
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=CheckoutResponse)
def create_portal(body: PortalRequest, db: DbSession) -> CheckoutResponse:
    try:
        url = billing.create_billing_portal_session(db, body.email)
    except billing.SubscriptionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this email",
        ) from exc
    if not url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe did not return a portal URL",
        )
    return CheckoutResponse(url=url)


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: DbSession) -> dict[str, bool]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = billing.construct_event(payload, sig_header)
    except billing.InvalidWebhookSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        ) from exc

    billing.handle_event(db, event)
    return {"received": True}
