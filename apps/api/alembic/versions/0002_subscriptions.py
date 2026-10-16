"""Add subscriptions table.

Revision ID: 0002_subscriptions
Revises: 0001_baseline
Create Date: 2026-10-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_subscriptions"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("price_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
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


def downgrade() -> None:
    op.drop_index("ix_subscriptions_stripe_subscription_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_stripe_customer_id", table_name="subscriptions")
    op.drop_table("subscriptions")
