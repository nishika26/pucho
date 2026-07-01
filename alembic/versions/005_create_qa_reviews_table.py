"""create qa_reviews table

Revision ID: 0005_create_qa_reviews_table
Revises: 0004_create_volunteer_and_expert_tables
Create Date: 2026-06-30

The approval queue: every domain-turn writes one `pending` row; a local
volunteer can attach `local_input`; an expert attaches `expert_input` and
either approves (triggers `ingest.py`) or rejects.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qa_reviews",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "domain",
            postgresql.ENUM(
                "legal", "healthcare", "financial",
                name="domain_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("user_question", sa.Text(), nullable=False),
        sa.Column("bot_answer", sa.Text(), nullable=False),
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("local_input", sa.Text(), nullable=True),
        sa.Column(
            "local_volunteer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("local_volunteers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expert_input", sa.Text(), nullable=True),
        sa.Column(
            "expert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("domain_experts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "documents_chunk_id",
            postgresql.UUID(as_uuid=True),
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
            "status IN ('pending','approved','rejected')",
            name="qa_reviews_status_check",
        ),
    )
    op.create_index("ix_qa_reviews_domain", "qa_reviews", ["domain"])
    # No separate status index: the (status, created_at) composite below serves
    # the dashboard's status-ordered list AND status-only lookups via its prefix.
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
    op.drop_index("ix_qa_reviews_domain", table_name="qa_reviews")
    op.drop_table("qa_reviews")
