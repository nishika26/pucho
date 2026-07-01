"""Local-volunteer model.

Volunteers log in to the dashboard (Streamlit) and add `local_input` to
pending qa_reviews. Each volunteer is a `users` row plus a 1:1 profile
row. The dashboard's auth path is keyed off `users.email + password_hash`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import text
from sqlmodel import Field, SQLModel


class LocalVolunteerBase(SQLModel):
    """Fields shared by LocalVolunteerModel (table) and LocalVolunteerCreate."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID = Field(
        foreign_key="dashboard_users.id",
        unique=True,
        index=True,
        ondelete="CASCADE",
        description="FK to the dashboard_users row (role='local_volunteer')",
    )
    name: str = Field(max_length=128)
    active: bool = Field(default=True)


class LocalVolunteerModel(LocalVolunteerBase, table=True):
    """ORM table for `local_volunteers`."""

    __tablename__ = "local_volunteers"

    id: UUID = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"server_default": text("gen_random_uuid()")},
    )
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


class LocalVolunteerCreate(LocalVolunteerBase):
    """Fields the app sets when registering a volunteer."""


__all__ = ["LocalVolunteerModel", "LocalVolunteerCreate"]