"""Auto-enqueue Q&A rows into the approval queue after each domain turn.

`create_pending_review(state, runtime, *, domain)` is wired into the router
graph as the `enqueue_review` node. It runs after `persist_message` so
`last_message_id` is set; it reads `input_question` (the user's question)
and `output_text` (the agent's reply) from state and writes one row into
`qa_reviews` with status='pending'.

The dashboard reads these rows; volunteers add `local_input`, experts add
`expert_input`, and an approve click triggers `services.knowledge.ingest`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.runtime import Runtime

import crud.qa_review as crud_qa_review
from models.memory import MemoryDomainLiteral
from models.qa_review import QAReviewCreate
from services.agent.router import RouterContext, State


async def create_pending_review(
    state: State,
    runtime: Runtime[RouterContext],
    *,
    domain: MemoryDomainLiteral,
) -> dict[str, Any]:
    """Insert one `pending` row into qa_reviews. No-op if state is empty.

    The user's question is `state["input_question"]`; the agent's reply is
    `state["output_text"]`. We skip if either is empty so partial fails
    don't pollute the queue.
    """
    question = (state.get("input_question") or "").strip()
    answer = (state.get("output_text") or "").strip()
    if not question and not answer:
        return {}

    source_message_id: UUID | None = state.get("last_message_id")
    payload = QAReviewCreate(
        domain=domain,
        user_question=question,
        bot_answer=answer,
        source_message_id=source_message_id,
    )
    row = await crud_qa_review.create(payload)
    return {"last_review_id": row.id}


__all__ = ["create_pending_review"]