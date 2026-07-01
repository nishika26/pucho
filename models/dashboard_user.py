"""Dashboard-user model.

`dashboard_users` is the reviewer identity table — volunteers, experts, and
admins who log in to the Streamlit dashboard with email + password. Their
profile rows live in `local_volunteers` / `domain_experts`, which FK to this
table.

WhatsApp senders are a separate population in `whatsapp_users`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel

from models.enums import DashboardRole, pg_enum


class DashboardUserBase(SQLModel):
    """Fields shared by DashboardUserModel and the Create/Update variants."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(max_length=128)
    email: str = Field(
        unique=True,
        index=True,
        max_length=255,
        description="Login identity for dashboard reviewers",
    )
    password_hash: str | None = Field(
        default=None,
        max_length=255,
        description="bcrypt hash; never logged or returned over the API",
    )
    role: DashboardRole = Field(
        sa_type=pg_enum(DashboardRole, "dashboard_role"),
        index=True,
        description="expert | local_volunteer | admin",
    )


class DashboardUserModel(DashboardUserBase, table=True):
    """ORM table for `dashboard_users`."""

    __tablename__ = "dashboard_users"

    id: UUID = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
    last_login_at: datetime | None = Field(default=None)
    created_at: datetime = Field(
        default=None, sa_column_kwargs={"server_default": text("now()")}
    )
    updated_at: datetime = Field(
        default=None,
        sa_column_kwargs={
            "server_default": text("now()"),
            "onupdate": text("now()"),
        },
    )


class DashboardUserCreate(DashboardUserBase):
    """Fields set when an admin creates a dashboard user."""


class DashboardUserUpdate(SQLModel):
    """Mutable subset — partial updates from the admin Users page."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = None
    email: str | None = None
    password_hash: str | None = None
    role: DashboardRole | None = None
    last_login_at: datetime | None = None


__all__ = [
    "DashboardUserModel",
    "DashboardUserCreate",
    "DashboardUserUpdate",
]
