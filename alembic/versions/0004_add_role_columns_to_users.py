"""add role + email + password_hash + last_login_at to users

Revision ID: 0004_add_role_columns_to_users
Revises: 0003_create_user_memories_table
Create Date: 2026-06-29

Adds dashboard-auth columns to the existing `users` table:
- role:           volunteer | expert | admin | NULL (NULL keeps current WhatsApp senders)
- email:          unique login identity for dashboard users (NULL = phone-only)
- password_hash:  bcrypt hash for dashboard login
- last_login_at:  touched by the dashboard on every successful login

All four columns are nullable so existing WhatsApp-sender rows remain valid.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_role_columns_to_users"
down_revision: Union[str, None] = "0003_create_user_memories_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=16),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Role is enforced via CHECK; existing rows keep role=NULL.
    op.create_check_constraint(
        "users_role_check",
        "users",
        "role IS NULL OR role IN ('volunteer','expert','admin')",
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"])


def downgrade() -> None:
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("users_role_check", "users", type_="check")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
