from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from stripe import StripeError

from app.api.deps import require_billing_admin, require_workspace_access
from app.core.db import get_session
from app.services import billing, plans

router = APIRouter(prefix="/v1/workspaces/{workspace_id}/billing", tags=["billing"])
catalog_router = APIRouter(prefix="/v1", tags=["billing"])
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

DbSession = Annotated[Session, Depends(get_session)]
AdminWorkspace = Annotated[UUID, Depends(require_billing_admin)]


class CheckoutRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class CheckoutResponse(BaseModel):
    url: str


class SubscriptionState(BaseModel):
    plan_code: str
    plan_name: str
    status: str
    max_knowledge_bases: int
    cancel_at_period_end: bool
    current_period_end: str | None


class PlanSummary(BaseModel):
    code: str
    name: str
    max_knowledge_bases: int


class PlanList(BaseModel):
    items: list[PlanSummary]


async def raw_body(request: Request) -> bytes:
    """Raw request body, required to verify the Stripe signature."""
    return await request.body()


@catalog_router.get("/plans", response_model=PlanList)
def list_plans() -> PlanList:
    """Public plan catalog."""
    return PlanList(
        items=[
            PlanSummary(
                code=plan.code,
                name=plan.name,
                max_knowledge_bases=plan.max_knowledge_bases,
            )
            for plan in plans.list_plans()
        ]
    )


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    workspace_id: str,
    body: CheckoutRequest,
    db: DbSession,
    admin_workspace: AdminWorkspace,
) -> CheckoutResponse:
    """Start the Pro subscription of a workspace."""
    target = require_workspace_access(workspace_id, admin_workspace)
    try:
        url = billing.create_checkout_session(db, workspace_id=target, email=body.email)
    except billing.SubscriptionAlreadyActive as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This workspace already has an active subscription",
        ) from exc
    except billing.StripeNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured",
        ) from exc
    except StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe rejected the checkout session",
        ) from exc
    return CheckoutResponse(url=url)


@router.post("/portal", response_model=CheckoutResponse)
def create_portal(
    workspace_id: str,
    db: DbSession,
    admin_workspace: AdminWorkspace,
) -> CheckoutResponse:
    """Open the Stripe billing portal of a workspace."""
    target = require_workspace_access(workspace_id, admin_workspace)
    try:
        url = billing.create_billing_portal_session(db, workspace_id=target)
    except billing.SubscriptionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found for this workspace",
        ) from exc
    except StripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe rejected the portal session",
        ) from exc
    return CheckoutResponse(url=url)


@router.get("/subscription", response_model=SubscriptionState)
def subscription_state(
    workspace_id: str,
    db: DbSession,
    admin_workspace: AdminWorkspace,
) -> SubscriptionState:
    """Current plan of a workspace, read from the persisted subscription."""
    target = require_workspace_access(workspace_id, admin_workspace)
    return SubscriptionState(**billing.get_subscription_state(db, workspace_id=target))


@webhook_router.post("/stripe")
def stripe_webhook(
    payload: Annotated[bytes, Depends(raw_body)],
    request: Request,
    db: DbSession,
) -> dict[str, bool]:
    """Receive a Stripe event.

    The signature is verified before anything is stored. The event is persisted
    and handed to the worker, so the answer does not wait for the Stripe API.
    """
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = billing.construct_event(payload, sig_header)
    except billing.InvalidWebhookSignature as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        ) from exc

    event_id = str(event["id"])
    stored = billing.record_event(db, event)
    if stored or billing.event_needs_processing(db, event_id):
        try:
            billing.enqueue_event(event_id)
        except Exception as exc:
            # The event is stored, so Stripe retries and the event is queued
            # again on the next delivery.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing worker is unavailable",
            ) from exc
    return {"received": True}
