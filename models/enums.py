"""Cross-cutting StrEnum + Literal types shared by the dashboard, KB, and auth.

Kept separate from `models/memory.py` so the senior-engineer doc's reviewer
flow can reuse the same domain literal without importing long-term-memory
machinery.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class ReviewerRole(StrEnum):
    """Role carried by `users.role`. NULL means a phone-only WhatsApp sender."""

    VOLUNTEER = "volunteer"
    EXPERT = "expert"
    ADMIN = "admin"


ReviewerRoleLiteral = Literal["volunteer", "expert", "admin"]


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
    "ReviewerRole",
    "ReviewerRoleLiteral",
    "QAReviewStatus",
    "QAReviewStatusLiteral",
    "DocumentSource",
    "DocumentSourceLiteral",
]