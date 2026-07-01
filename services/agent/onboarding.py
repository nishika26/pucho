"""First-contact onboarding — a single warm welcome for brand-new users.

Runs as a router node *before* classification, only when the WhatsApp user
isn't onboarded yet. It is deliberately light and literacy-friendly:

- One short, warm message (works read-aloud for non-readers — TTS for voice).
- Written in the user's own language (Hindi / Marathi / English / Hinglish).
- Explains in plain words what Pucho helps with and that voice OR text is fine.
- Captures their first name if they happened to give one (never invented).
- Marks the user onboarded and invites their question.

It does NOT answer the user's question this turn — the welcome sets
expectations first; the user's next message flows through the normal
router → domain path.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

import crud.message as crud_message
import crud.whatsapp_user as crud_whatsapp_user
from services.agent.router import RouterContext, State, make_thread_id

ONBOARDING_SYSTEM_PROMPT = """You are Pucho, a free WhatsApp helper for low-income families in India, onboarding a NEW user. You are told the user's KNOWN name (may be "unknown").

From the user's message, extract:
- name: their first name if they state it in THIS message, else null.
- locality: where they live (their area / town / village / city) if they state it, else null.
- welcome: a SHORT, warm message following the rules below.

Language rules (follow exactly): if the user wrote in Devanagari Hindi, reply in Hindi; if in Marathi, reply in Marathi; if in English OR Hinglish (anything in Latin/Roman letters, including a plain "hi"), reply in warm simple HINGLISH (Hindi in Latin letters mixed with common English words) — never formal English. Only use pure Hindi once the user writes in Devanagari.

Welcome rules:
- Very simple everyday words (it may be read ALOUD to someone who cannot read). No jargon, no lists, no markdown.
- At most 3 short sentences.
- If the user has NOT given their name yet (known name is "unknown" and they didn't give it now): warmly introduce Pucho in one line (helps with legal, health, and money/government-scheme questions, by voice or text), then ask them their name and where they live — e.g. in Hinglish: "Kya aap mujhe apna naam bata sakte hain, aur aap kahaan rehte hain?"
- If the user HAS given their name (now or already known): greet them warmly by name, thank them, and invite them to say what they need help with.

Never invent a name or locality — use null if not clearly stated.
"""


class Onboarding(BaseModel):
    """Structured output for the onboarding step."""

    name: str | None = Field(
        default=None,
        description="The user's first name if they clearly stated it, else null.",
    )
    locality: str | None = Field(
        default=None,
        description="Where the user lives (area/town/village/city) if stated, else null.",
    )
    welcome: str = Field(description="The warm welcome message, in the user's language.")


async def run(state: State, runtime: Runtime[RouterContext]) -> dict[str, Any]:
    """Onboard a new user over up to two turns: greet + ask for name & locality,
    then capture them and finish.

    Only called when `runtime.context.onboarded` is False. We mark the user
    onboarded only once we know their name (from this message or already
    stored), so the "what's your name / where do you live" reply is captured
    instead of being routed to a domain agent. Short-circuits the graph.
    """
    question = (state.get("input_question") or "").strip()
    modality = state.get("modality") or "text"
    user_id = runtime.context.user_id
    known_name = runtime.context.name  # None until we've captured it

    from config.settings import settings

    model = ChatOpenAI(
        model=os.environ.get("PUCHO_ROUTER_MODEL", "gpt-4o-mini"),
        api_key=settings.OPENAI_API_KEY,
    )
    onboarder = model.with_structured_output(Onboarding)
    result: Onboarding = await onboarder.ainvoke(
        [
            SystemMessage(content=ONBOARDING_SYSTEM_PROMPT),
            SystemMessage(content=f"Known name: {known_name or 'unknown'}"),
            HumanMessage(content=question or "(the user sent a greeting with no text)"),
        ]
    )

    if result.name:
        await crud_whatsapp_user.set_name(user_id, result.name)
    if result.locality:
        await crud_whatsapp_user.set_locality(user_id, result.locality)

    # Finish onboarding only once we have a name (now or already stored); until
    # then we keep asking, so their name/locality reply isn't sent to a domain.
    if result.name or known_name:
        await crud_whatsapp_user.mark_onboarded(user_id)

    # Persist the welcome to the audit log ourselves (we skip persist_message).
    await crud_message.create_message(
        user_id=user_id,
        thread_id=make_thread_id(runtime.context.phone_number),
        role="ai",
        modality=modality,
        content=result.welcome,
    )

    output_audio_url: str | None = None
    if modality == "voice":
        # Lazy import avoids an import cycle at module load (audio ↔ router).
        from api.routes.whatsapp.audio import synthesize_and_upload

        language = state.get("language") or "hi-IN"
        output_audio_url = await synthesize_and_upload(
            result.welcome, language=language, prefix="onboarding"
        )

    return {
        "output_text": result.welcome,
        "output_audio_url": output_audio_url,
        "onboarding_handled": True,
        "messages": [AIMessage(content=result.welcome)],
    }


__all__ = ["run"]
