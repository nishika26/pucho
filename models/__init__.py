"""Pydantic v2 / SQLModel definitions for the project tables.

Submodules:
    user         — `users` table + auth columns
    enums        — Enum + Literal cross-cuts (reviewer role, QA status, doc source)
    volunteer    — `local_volunteers`
    expert       — `domain_experts`
    qa_review    — approval queue
    memory       — long-term memory (user_memories)
    message      — audit log (messages)
    document     — RAG knowledge base (documents)

Naming follows the senior-engineer doc: prefix with the domain noun
(WhatsAppUserModel, DashboardUserModel, QAReviewModel, …). All tables share
`model_config = ConfigDict(from_attributes=True)`.

Importing this package imports every table model, so `SQLModel.metadata` is
fully populated. Alembic's `env.py` relies on this (`import models`) — without
it, autogenerate would only see the modules it happened to import and would
emit DROPs for the rest.
"""

from models.dashboard_user import DashboardUserModel
from models.document import DocumentCreate, DocumentModel
from models.expert import DomainExpertModel
from models.memory import UserMemoryModel
from models.message import MessageModel
from models.qa_review import QAReviewModel
from models.volunteer import LocalVolunteerModel
from models.whatsapp_user import WhatsAppUserModel

__all__ = [
    "DashboardUserModel",
    "DocumentCreate",
    "DocumentModel",
    "DomainExpertModel",
    "LocalVolunteerModel",
    "MessageModel",
    "QAReviewModel",
    "UserMemoryModel",
    "WhatsAppUserModel",
]