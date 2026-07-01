"""create local_volunteers and domain_experts tables

Revision ID: 0004_create_volunteer_and_expert_tables
Revises: 0003_create_user_memories_table
Create Date: 2026-06-30

Reviewer profile tables, both FK to `dashboard_users`:
- `local_volunteers`: 1:1 with a dashboard_user (role='local_volunteer').
- `domain_experts`: one row per (user_id, domain). Carries credential data
  (highest_education, work_status, verified) used by the admin to vet experts.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_volunteers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dashboard_users.id", ondelete="CASCADE"),
            nullable=False,
            # Uniqueness comes from the explicit unique index below.
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
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
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dashboard_users.id", ondelete="CASCADE"),
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
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "highest_education",
            postgresql.ENUM(
                "high_school", "diploma", "bachelors", "masters", "doctorate",
                name="education_level",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "work_status",
            postgresql.ENUM(
                "working", "student",
                name="work_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.UniqueConstraint(
            "user_id", "domain", name="domain_experts_user_id_domain_uniq"
        ),
    )
    # (user_id, domain) unique constraint already covers user_id lookups
    # (list_for_user); only the domain-only lookup (list_for_domain) needs its
    # own index.
    op.create_index("ix_domain_experts_domain", "domain_experts", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_domain_experts_domain", table_name="domain_experts")
    op.drop_table("domain_experts")
    op.drop_index("ix_local_volunteers_user_id", table_name="local_volunteers")
    op.drop_table("local_volunteers")
