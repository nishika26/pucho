"""create user_memories table

Revision ID: 0003_create_user_memories_table
Revises: 0002_create_messages_table
Create Date: 2026-06-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("whatsapp_users.id", ondelete="CASCADE"),
            nullable=False,
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
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
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
            "confidence >= 0.0 AND confidence <= 1.0",
            name="user_memories_confidence_check",
        ),
        sa.UniqueConstraint(
            "user_id", "domain", "key",
            name="user_memories_user_id_domain_key_uniq",
        ),
    )
    # No separate user_id index: the (user_id, domain, key) unique constraint
    # already covers (user_id) and (user_id, domain) lookups via its prefix.
    op.create_index("ix_user_memories_domain", "user_memories", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_user_memories_domain", table_name="user_memories")
    op.drop_table("user_memories")
