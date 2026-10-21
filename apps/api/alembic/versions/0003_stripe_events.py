"""Add stripe_events table.

Stores the verified Stripe events. The Stripe event id is the primary key, so
a redelivered event can never create a second row.

Revision ID: 0003_stripe_events
Revises: 0002_subscriptions
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_stripe_events"
down_revision: str | None = "0002_subscriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="received"
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
