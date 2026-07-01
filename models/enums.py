"""Cross-cutting Enum + Literal types shared by the dashboard, KB, and auth.

Kept separate from `models/memory.py` so the senior-engineer doc's reviewer
flow can reuse the same domain literal without importing long-term-memory
machinery.

`pg_enum()` builds a NATIVE Postgres enum column type. By default SQLAlchemy
stores the enum *member name* ("LEGAL"); we pass `values_callable` so it stores
the *value* ("legal") — matching the lowercase strings the rest of the app and
the migrations use.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

import sqlalchemy as sa


def pg_enum(py_enum: type[StrEnum], name: str) -> sa.Enum:
    """A native Postgres ENUM column type that stores enum *values*."""
    return sa.Enum(
        py_enum,
        name=name,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class DashboardRole(StrEnum):
    """Role carried by `dashboard_users.role`. Only dashboard reviewers exist
    in that table — WhatsApp senders live in a separate `whatsapp_users` table.
    """

    EXPERT = "expert"
    LOCAL_VOLUNTEER = "local_volunteer"
    ADMIN = "admin"


DashboardRoleLiteral = Literal["expert", "local_volunteer", "admin"]

# Backwards-compatible aliases — older modules import `ReviewerRole`.
ReviewerRole = DashboardRole
ReviewerRoleLiteral = DashboardRoleLiteral


class WorkStatus(StrEnum):
    """Whether a domain expert is currently working or studying."""

    WORKING = "working"
    STUDENT = "student"


WorkStatusLiteral = Literal["working", "student"]


class LiteracyLevel(StrEnum):
    """How comfortably a WhatsApp user reads/writes — drives reply complexity.

    Persisted on `whatsapp_users` as a running profile (stabilises over time);
    seeded from modality (voice => low) and refined by the router classifier.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


LiteracyLevelLiteral = Literal["low", "medium", "high"]


class EmotionalTone(StrEnum):
    """Per-message emotional read used to shape the reply's framing. Not
    persisted — it's a property of the message, not the person.
    """

    NEUTRAL = "neutral"
    WORRIED = "worried"
    DISTRESSED = "distressed"
    FRUSTRATED = "frustrated"
    HOPEFUL = "hopeful"


EmotionalToneLiteral = Literal[
    "neutral", "worried", "distressed", "frustrated", "hopeful"
]


class EducationLevel(StrEnum):
    """Highest education completed by a domain expert."""

    HIGH_SCHOOL = "high_school"
    DIPLOMA = "diploma"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    DOCTORATE = "doctorate"


EducationLevelLiteral = Literal[
    "high_school", "diploma", "bachelors", "masters", "doctorate"
]


class QAReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


QAReviewStatusLiteral = Literal["pending", "approved", "rejected"]


class DocumentSource(StrEnum):
    """How a `documents` row was created."""

    MANUAL = "manual"  # scripts/seed_documents.py
    EXPERT_APPROVED = "expert_approved"  # dashboard ingest pipeline


DocumentSourceLiteral = Literal["manual", "expert_approved"]


__all__ = [
    "pg_enum",
    "DashboardRole",
    "DashboardRoleLiteral",
    "ReviewerRole",
    "ReviewerRoleLiteral",
    "WorkStatus",
    "WorkStatusLiteral",
    "LiteracyLevel",
    "LiteracyLevelLiteral",
    "EmotionalTone",
    "EmotionalToneLiteral",
    "EducationLevel",
    "EducationLevelLiteral",
    "QAReviewStatus",
    "QAReviewStatusLiteral",
    "DocumentSource",
    "DocumentSourceLiteral",
]
