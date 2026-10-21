"""Add subscriptions table.

The shape follows ADR 0001: the workspace owns the billing and holds at most
one current subscription. The workspace foreign key is added in a later
migration, when the workspaces table lands.

Revision ID: 0002_subscriptions
Revises: 0001_baseline
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_subscriptions"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENT_STATUSES = ("trialing", "active", "past_due", "unpaid", "paused")
CURRENT_STATUS_SQL = ", ".join(f"'{status}'" for status in CURRENT_STATUSES)


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column(
            "plan_code", sa.String(length=50), nullable=False, server_default="free"
        ),
        sa.Column(
            "status", sa.String(length=50), nullable=False, server_default="incomplete"
        ),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscriptions_workspace_id",
        "subscriptions",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_subscriptions_stripe_customer_id",
        "subscriptions",
        ["stripe_customer_id"],
        unique=True,
    )
    op.create_index(
        "ix_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
        unique=True,
    )
    op.create_index(
        "uq_subscriptions_current_per_workspace",
        "subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({CURRENT_STATUS_SQL})"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_current_per_workspace", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_workspace_id", table_name="subscriptions")
    op.drop_table("subscriptions")
