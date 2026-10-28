"""Persist ingestion intent atomically with documents.

Revision ID: 0003_document_outbox
Revises: 0002_document_ingestion_pgvector
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_document_outbox"
down_revision: str | None = "0002_document_ingestion_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(200)),
        sa.UniqueConstraint("document_id", name="uq_document_outbox_document"),
    )
    op.create_index(
        "ix_document_outbox_due",
        "document_outbox",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("published_at IS NULL AND processed_at IS NULL"),
    )
    # Recover old uploads without replaying successful/processing documents.
    op.execute(
        sa.text("""
        INSERT INTO document_outbox (id, document_id)
        SELECT gen_random_uuid(), id FROM documents
        WHERE status = 'PENDING'
           OR (status = 'FAILED' AND failure_reason =
               'document could not be queued for processing')
    """)
    )
    op.execute(
        sa.text("""
        UPDATE documents SET status = 'PENDING', failure_reason = NULL
        WHERE status = 'FAILED' AND failure_reason =
              'document could not be queued for processing'
    """)
    )


def downgrade() -> None:
    op.drop_table("document_outbox")
