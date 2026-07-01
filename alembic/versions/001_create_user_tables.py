"""create shared enums + whatsapp_users and dashboard_users tables

Revision ID: 0001_create_enums_and_user_tables
Revises:
Create Date: 2026-06-30

Two distinct user populations live in two separate tables:
- `whatsapp_users`  — bot end-users, identified by `whatsapp_number`.
- `dashboard_users` — reviewers (expert/local_volunteer/admin) who log in
  with email + password.

All native enum TYPEs are created up front so later migrations can reference
them with `create_type=False`.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Native enum types (created once, reused by later migrations).
    op.execute("CREATE TYPE domain_enum AS ENUM ('legal', 'healthcare', 'financial')")
    op.execute(
        "CREATE TYPE dashboard_role AS ENUM ('expert', 'local_volunteer', 'admin')"
    )
    op.execute("CREATE TYPE work_status AS ENUM ('working', 'student')")
    op.execute(
        "CREATE TYPE education_level AS ENUM "
        "('high_school', 'diploma', 'bachelors', 'masters', 'doctorate')"
    )
    op.execute("CREATE TYPE literacy_level AS ENUM ('low', 'medium', 'high')")

    op.create_table(
        "whatsapp_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Uniqueness comes from the explicit unique index below (avoids a
        # duplicate UNIQUE constraint + index on the same column).
        sa.Column("whatsapp_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("locality", sa.String(length=128), nullable=True),
        sa.Column(
            "literacy_level",
            postgresql.ENUM(
                "low", "medium", "high",
                name="literacy_level",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "onboarded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
        "ix_whatsapp_users_whatsapp_number",
        "whatsapp_users",
        ["whatsapp_number"],
        unique=True,
    )

    op.create_table(
        "dashboard_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        # Uniqueness comes from the explicit unique index below.
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(
                "expert", "local_volunteer", "admin",
                name="dashboard_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_dashboard_users_email", "dashboard_users", ["email"], unique=True)
    op.create_index("ix_dashboard_users_role", "dashboard_users", ["role"])


def downgrade() -> None:
    op.drop_index("ix_dashboard_users_role", table_name="dashboard_users")
    op.drop_index("ix_dashboard_users_email", table_name="dashboard_users")
    op.drop_table("dashboard_users")
    op.drop_index("ix_whatsapp_users_whatsapp_number", table_name="whatsapp_users")
    op.drop_table("whatsapp_users")
    op.execute("DROP TYPE IF EXISTS literacy_level")
    op.execute("DROP TYPE IF EXISTS education_level")
    op.execute("DROP TYPE IF EXISTS work_status")
    op.execute("DROP TYPE IF EXISTS dashboard_role")
    op.execute("DROP TYPE IF EXISTS domain_enum")
