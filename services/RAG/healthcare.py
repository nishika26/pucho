"""healthcare-domain agent.

Retrieves from the healthcare corpus, injects the user's stored healthcare facts
into the system prompt, answers the user's question, and produces a voice
reply (TTS → Vercel Blob upload) when the user's original modality was voice.

The agent's `run` is a LangGraph node body — it takes `(state, runtime)` and
reads `runtime.context.user_id` to scope memory lookups.
"""

from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime
from langchain_openai import ChatOpenAI 

import crud.memory as crud_memory
from api.routes.whatsapp.audio import synthesize_and_upload
from models.memory import MemoryDomain
from services.agent.retriever import get_retriever
from services.agent.router import RouterContext, State
from services.agent.style import build_system_prompt
from services.memory.inject import format_memories_for_prompt

_retriever = get_retriever("healthcare")


async def _format_context(question: str) -> str:
    docs = await _retriever.retrieve(question, k=4)
    if not docs:
        return "(no documents retrieved)"
    blocks = [f"[{i}] {doc.page_content}" for i, doc in enumerate(docs, start=1)]
    return "\n\n".join(blocks)


async def run(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    """Domain node: invoked by the router graph."""
    question: str = state["input_question"]
    language: str = state.get("language") or "en-IN"
    modality: str = state["modality"]
    user_id = runtime.context.user_id

    # Retrieve with the English search query (matches the English corpus); the
    # answer is still generated from `question` in the user's own language.
    search_query = state.get("search_query") or question
    context = await _format_context(search_query)
    memories = await crud_memory.list_for_user_domain(user_id, MemoryDomain.healthcare)
    memory_block = format_memories_for_prompt(memories)

    # Get last 3 turns (6 messages) for conversation history
    history_messages = state.get("messages", [])
    if len(history_messages) > 6:
        history_messages = history_messages[-6:]  # Keep last 3 user+assistant pairs

    system = build_system_prompt(
        domain="healthcare",
        literacy=state.get("literacy_level"),
        tone=state.get("emotional_tone"),
        modality=modality,
        memory_block=memory_block,
        context=context,
    )

    from config.settings import settings

    model = ChatOpenAI(
        model=os.environ.get("PUCHO_healthcare_MODEL", "gpt-4o-mini"),
        api_key=settings.OPENAI_API_KEY,
    )
    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=system,
    )

    # Pass conversation history + current question to the agent
    current_message = [HumanMessage(content=question)]
    all_messages = history_messages + current_message

    result = await agent.ainvoke(
        {"messages": all_messages},
        config={"configurable": {"thread_id": f"healthcare-{user_id}"}},  # Use user_id for uniqueness
    )

    final_text = result["messages"][-1].content
    if isinstance(final_text, list):
        final_text = "".join(part.get("text", "") for part in final_text)

    output_audio_url: str | None = None
    if modality == "voice":
        output_audio_url = await synthesize_and_upload(
            final_text, language=language, prefix="healthcare"
        )

    # Append BOTH sides of this turn (user question + bot reply) so the
    # add_messages reducer accumulates them into the running short-term history.
    return {
        "output_text": final_text,
        "output_audio_url": output_audio_url,
        "messages": [HumanMessage(content=question), AIMessage(content=final_text)],
    }