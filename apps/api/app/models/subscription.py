from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Subscription states defined by ADR 0001. They match the Stripe subscription
# statuses one to one.
SUBSCRIPTION_STATUSES = (
    "trialing",
    "active",
    "past_due",
    "unpaid",
    "paused",
    "canceled",
    "incomplete",
    "incomplete_expired",
)

# Statuses that count as a current subscription. ADR 0001 allows at most one
# current subscription per workspace.
CURRENT_SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "unpaid", "paused")

_CURRENT_STATUS_SQL = ", ".join(
    f"'{status}'" for status in CURRENT_SUBSCRIPTION_STATUSES
)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # Nullable until the workspaces table lands; the foreign key is added in a
    # later migration. ADR 0001 makes the workspace the owner of the billing.
    workspace_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="incomplete"
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Timestamp of the last Stripe event applied, used to ignore events that
    # arrive out of order.
    last_event_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "uq_subscriptions_current_per_workspace",
            "workspace_id",
            unique=True,
            postgresql_where=text(f"status IN ({_CURRENT_STATUS_SQL})"),
            sqlite_where=text(f"status IN ({_CURRENT_STATUS_SQL})"),
        ),
    )
