"""Pydantic v2 / SQLModel definitions for the project tables.

Submodules:
    user         — `users` table + auth columns
    enums        — StrEnum + Literal cross-cuts (reviewer role, QA status, doc source)
    volunteer    — `local_volunteers`
    expert       — `domain_experts`
    qa_review    — approval queue
    memory       — long-term memory (user_memories)
    message      — audit log (messages)
    document     — RAG knowledge base (documents)

Naming follows the senior-engineer doc: prefix with the domain noun
(UserModel, QAReviewModel, …). All tables share `model_config = ConfigDict(from_attributes=True)`.
"""