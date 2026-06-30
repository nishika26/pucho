"""Financial-domain agent.

Retrieves from the financial corpus, injects the user's stored financial
facts into the system prompt, answers the user's question, and produces a
voice reply (TTS → Vercel Blob upload) when the user's original modality was
voice.

The agent's `run` is a LangGraph node body — it takes `(state, runtime)` and
reads `runtime.context.user_id` to scope memory lookups.
"""

from __future__ import annotations

import os
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

import crud.memory as crud_memory
from api.routes.whatsapp.audio import synthesize_and_upload
from models.memory import MemoryDomain
from services.agents.retriever import get_retriever
from services.agents.router import RouterContext, State
from services.memory.inject import format_memories_for_prompt

SYSTEM_PROMPT = """You are the financial-domain assistant for Pucho, a WhatsApp chatbot.

Rules:
- Answer ONLY from the retrieved financial documents provided to you.
- If the documents do not contain the answer, say so plainly and recommend the
  user consult a qualified financial advisor. Do not invent rates, returns,
  tax figures, or product terms.
- Do NOT provide legal or medical advice even if asked.
- Match the user's language (read it from the conversation context).
- Keep replies concise — WhatsApp messages render poorly past ~1500 chars.
- The surrounding system handles TTS for voice replies, so just produce the
  answer as text. Do not try to call any audio tools yourself.
- When the user mentions personal facts relevant to financial advice (income
  bracket, tax bracket, existing loans, investments, etc.), those are
  surfaced separately as "Known facts" — use them, do not re-ask.
"""

_retriever = get_retriever("financial")


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

    context = await _format_context(question)
    memories = await crud_memory.list_for_user_domain(user_id, MemoryDomain.FINANCIAL)
    memory_block = format_memories_for_prompt(memories)

    system = (
        SYSTEM_PROMPT
        + f"\n\nUser language: {language}\nUser modality: {modality}"
        + (f"\n\n{memory_block}" if memory_block else "")
        + f"\n\nRetrieved financial documents:\n{context}"
    )

    from langchain_openai import ChatOpenAI  # local import keeps module light
    model = ChatOpenAI(model=os.environ.get("PUCHO_FINANCIAL_MODEL", "gpt-4o-mini"))
    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=system,
    )

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config={"configurable": {"thread_id": "pucho-financial"}},
    )

    final_text = result["messages"][-1].content
    if isinstance(final_text, list):
        final_text = "".join(part.get("text", "") for part in final_text)

    output_audio_url: str | None = None
    if modality == "voice":
        output_audio_url = await synthesize_and_upload(
            final_text, language=language, prefix="financial"
        )

    return {
        "output_text": final_text,
        "output_audio_url": output_audio_url,
        "messages": [AIMessage(content=final_text)],
    }