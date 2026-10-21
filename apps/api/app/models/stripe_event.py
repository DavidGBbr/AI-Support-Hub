from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Lifecycle of a stored Stripe event.
EVENT_STATUS_RECEIVED = "received"
EVENT_STATUS_PROCESSED = "processed"
EVENT_STATUS_FAILED = "failed"


class StripeEvent(Base):
    """Raw Stripe event, stored for idempotency and replay.

    The Stripe event id is the primary key, so a redelivered event can never
    create a second row.
    """

    __tablename__ = "stripe_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    livemode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=EVENT_STATUS_RECEIVED
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
