"""create qa_reviews table

Revision ID: 0006_create_qa_reviews_table
Revises: 0005_create_volunteer_expert_tables
Create Date: 2026-06-29

The approval queue per the senior-engineer doc: every domain-turn writes one
`pending` row; a local volunteer can attach `local_input`; an expert attaches
`expert_input` and either approves (which triggers `ingest.py`) or rejects.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_create_qa_reviews_table"
down_revision: Union[str, None] = "0005_create_volunteer_expert_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_reviews",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.String(length=16), nullable=False),
        sa.Column("user_question", sa.Text(), nullable=False),
        sa.Column("bot_answer", sa.Text(), nullable=False),
        sa.Column(
            "source_message_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("local_input", sa.Text(), nullable=True),
        sa.Column(
            "local_volunteer_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("local_volunteers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expert_input", sa.Text(), nullable=True),
        sa.Column(
            "expert_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("domain_experts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # documents_chunk_id is forward-referenced by migration 0007.
        # Kept here as nullable UUID so a single approval updates this column
        # post-ingest without re-writing the row.
        sa.Column(
            "documents_chunk_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "domain IN ('legal','medical','financial')",
            name="qa_reviews_domain_check",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="qa_reviews_status_check",
        ),
    )
    op.create_index("ix_qa_reviews_domain", "qa_reviews", ["domain"])
    op.create_index("ix_qa_reviews_status", "qa_reviews", ["status"])
    # Dashboard default view: pending reviews sorted by newest first.
    op.create_index(
        "ix_qa_reviews_status_created_at",
        "qa_reviews",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_qa_reviews_source_message_id",
        "qa_reviews",
        ["source_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_qa_reviews_source_message_id", table_name="qa_reviews")
    op.drop_index("ix_qa_reviews_status_created_at", table_name="qa_reviews")
    op.drop_index("ix_qa_reviews_status", table_name="qa_reviews")
    op.drop_index("ix_qa_reviews_domain", table_name="qa_reviews")
    op.drop_table("qa_reviews")
