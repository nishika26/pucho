"""create local_volunteers and domain_experts tables

Revision ID: 0005_create_volunteer_expert_tables
Revises: 0004_add_role_columns_to_users
Create Date: 2026-06-29

Dashboard reviewers:
- `local_volunteers`: a volunteer profile linked 1:1 to a `users` row
  (the volunteer logs in with their own email/password).
- `domain_experts`: an expert profile scoped to one of the legal/medical/financial
  domains. A user may be an expert for multiple domains (UNIQUE (user_id, domain)).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_create_volunteer_expert_tables"
down_revision: Union[str, None] = "0004_add_role_columns_to_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_volunteers",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("preferred_language", sa.String(length=16), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
    )
    op.create_index(
        "ix_local_volunteers_user_id", "local_volunteers", ["user_id"], unique=True
    )

    op.create_table(
        "domain_experts",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=16), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
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
            name="domain_experts_domain_check",
        ),
        sa.UniqueConstraint("user_id", "domain", name="domain_experts_user_id_domain_uniq"),
    )
    op.create_index("ix_domain_experts_user_id", "domain_experts", ["user_id"])
    op.create_index("ix_domain_experts_domain", "domain_experts", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_domain_experts_domain", table_name="domain_experts")
    op.drop_index("ix_domain_experts_user_id", table_name="domain_experts")
    op.drop_table("domain_experts")
    op.drop_index("ix_local_volunteers_user_id", table_name="local_volunteers")
    op.drop_table("local_volunteers")
