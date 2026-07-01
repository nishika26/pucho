"""Simulate a 1-week usage journey for each persona through the REAL router graph.

For every WhatsApp persona this plays their 7-day message script through
`router_workflow.ainvoke(...)` — the exact pipeline a live WhatsApp message
hits — and prints, per turn, the bot's reply plus the personalisation signals
(domain routed to, inferred literacy, emotional tone). After the week it dumps
what the bot remembered about that user. Finally `--enrich` runs the
volunteer + expert (Hema) human-in-the-loop loop on a real pending Q&A.

Requirements to RUN: a working DATABASE_URL and OPENAI_API_KEY in .env. Each
turn makes ~3 LLM calls (classify + domain agent + reflect), so a full run is
~70 cheap gpt-4o-mini calls — a few cents total.

Usage:
    uv run python scripts/simulate.py                  # all 4 WhatsApp personas
    uv run python scripts/simulate.py --reset          # wipe prior data first (fresh onboarding)
    uv run python scripts/simulate.py --persona mohan  # just one
    uv run python scripts/simulate.py --enrich         # + the Hema enrichment loop
    uv run python scripts/simulate.py --no-whatsapp --enrich   # only the enrichment loop
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Repo root on the path (for crud/services imports); scripts/ is already
# sys.path[0], so `from personas import ...` resolves the sibling config.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from personas import (  # noqa: E402
    HEMA_EXPERT_EMAIL,
    VOLUNTEER_EMAIL,
    WHATSAPP_PERSONAS,
    Persona,
)
from services.agent import compile_router, make_thread_id  # noqa: E402
from services.agent.router import RouterContext  # noqa: E402

_RULE = "=" * 72


async def _exec(sql: str, params: dict | None = None) -> None:
    """Run a single statement in its own transaction (failures don't poison others)."""
    from sqlalchemy import text

    from config.db import get_session

    try:
        async with get_session() as session:
            await session.execute(text(sql), params or {})
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        print(f"    (skip: {exc.__class__.__name__})")


async def _reset_persona(persona: Persona) -> None:
    """Wipe a persona's prior data so onboarding + memory start fresh."""
    thread = make_thread_id(persona.phone)
    # CASCADE removes their messages + user_memories.
    await _exec(
        "DELETE FROM whatsapp_users WHERE whatsapp_number = :p", {"p": persona.phone}
    )
    # Clear the checkpointer's short-term memory for this thread.
    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
        await _exec(f"DELETE FROM {table} WHERE thread_id = :t", {"t": thread})


async def _run_turn(workflow, persona: Persona, message: str) -> dict:
    """Persist the inbound message (like the adapter does), then run the graph."""
    import crud.message as crud_message
    import crud.whatsapp_user as crud_wa

    user = await crud_wa.get_or_create_by_whatsapp_number(persona.phone)
    inbound = await crud_message.create_message(
        user_id=user.id,
        thread_id=make_thread_id(persona.phone),
        role="human",
        modality="text",
        content=message,
    )
    state: dict = {
        "input_question": message,
        "language": "en-IN",
        "modality": "text",
        "audio_bytes": None,
    }
    if user.literacy_level is not None:
        state["literacy_level"] = user.literacy_level

    context = RouterContext(
        user_id=user.id,
        phone_number=persona.phone,
        inbound_message_id=inbound.id,
        onboarded=user.onboarded,
        name=user.name,
    )
    return await workflow.ainvoke(
        state,
        context=context,
        config={"configurable": {"thread_id": make_thread_id(persona.phone)}},
    )


def _print_turn(persona: Persona, message: str, final: dict) -> None:
    reply = (final.get("output_text") or "").strip()
    if final.get("onboarding_handled"):
        signal = "onboarding (welcome)"
    else:
        signal = (
            f"domain={final.get('decision')} | "
            f"literacy={final.get('literacy_level')} | "
            f"tone={final.get('emotional_tone')}"
        )
    print(f"\n  👤 ({persona.modality})  {message}")
    print(f"  🤖  {reply}")
    print(f"      ↳ [{signal}]")


async def _dump_memories(persona: Persona) -> None:
    import crud.memory as crud_memory
    import crud.whatsapp_user as crud_wa
    from models.memory import MemoryDomain

    user = await crud_wa.get_by_whatsapp_number(persona.phone)
    if user is None:
        return
    print(f"\n  🧠 What Pucho learned about {persona.name} (literacy={user.literacy_level}):")
    found = False
    for domain in MemoryDomain:
        for fact in await crud_memory.list_for_user_domain(user.id, domain):
            found = True
            print(f"      - [{domain.value}] {fact.key}: {fact.value}")
    if not found:
        print("      (no durable facts extracted)")


async def _generate_persona_message(
    persona: Persona, seed: str, transcript: list[tuple[str, str]]
) -> str:
    """Write the persona's next message in-character and in their language.

    `seed` is the scripted intent for this turn; an LLM rewrites it the way this
    person would actually text it, in `persona.language`, staying consistent
    with the conversation so far. Used only with --llm.
    """
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from config.settings import settings

    lang_instruction = {
        "Hindi": "Hindi in the Devanagari script (देवनागरी). Do NOT use English or Latin letters.",
        "Marathi": "Marathi in the Devanagari script. Do NOT use English or Latin letters.",
        "Hinglish": "Hinglish — Hindi written in Latin/Roman letters mixed with common English words. Not pure English, not Devanagari.",
        "English": "simple English.",
    }.get(persona.language, persona.language)

    convo = "\n".join(f"{who}: {txt}" for who, txt in transcript[-6:]) or "(none yet)"
    system = SystemMessage(
        content=(
            "You are role-playing a WhatsApp user of a helpline. Stay fully in "
            f"character.\nYou are {persona.name} — {persona.blurb}. You live in "
            f"{persona.locality}.\nWrite in {lang_instruction} The way a real "
            "person of your background actually texts — simple, natural, first "
            "person. Do NOT introduce yourself or give your name (they already "
            "know you). Output ONLY your next message (1-2 short sentences): no "
            "quotes, no narration, no translation."
        )
    )
    human = HumanMessage(
        content=(
            f"Conversation so far:\n{convo}\n\n"
            f"What you want to say/ask now: {seed}\n\n"
            "Write your next WhatsApp message."
        )
    )
    llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)
    result = await llm.ainvoke([system, human])
    text = result.content
    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text)
    return text.strip()


async def simulate_persona(
    workflow, persona: Persona, *, reset: bool, use_llm: bool = False
) -> None:
    print(f"\n{_RULE}\n  {persona.name.upper()} — {persona.blurb}")
    print(
        f"  {persona.locality} · {persona.modality}-first · literacy={persona.literacy}"
        f" · lang={persona.language}\n{_RULE}"
    )

    if reset:
        await _reset_persona(persona)

    # Seed the literacy profile so personalisation reflects the real channel
    # (voice/illiterate => low) from the very first answer.
    import crud.whatsapp_user as crud_wa

    user = await crud_wa.get_or_create_by_whatsapp_number(persona.phone)
    await crud_wa.set_literacy_level(user.id, persona.literacy)
    # Pre-onboard: we already know the persona's name + locality, so skip the
    # interactive onboarding turns and go straight to real Q&A. (Onboarding
    # itself is demonstrated live on WhatsApp.)
    await crud_wa.set_name(user.id, persona.name)
    await crud_wa.set_locality(user.id, persona.locality)
    await crud_wa.mark_onboarded(user.id)

    transcript: list[tuple[str, str]] = []
    last_day = None
    for day, seed in persona.script:
        if day != last_day:
            print(f"\n  ----- Day {day} -----")
            last_day = day
        message = (
            await _generate_persona_message(persona, seed, transcript)
            if use_llm
            else seed
        )
        final = await _run_turn(workflow, persona, message)
        transcript.append(("User", message))
        transcript.append(("Pucho", (final.get("output_text") or "").strip()))
        _print_turn(persona, message, final)

    await _dump_memories(persona)


# Volunteer local tips + expert enrichment notes, one per domain.
_LOCAL_TIPS = {
    "legal": "Local tip: the ward office runs a free legal-aid help-desk on Tuesdays.",
    "healthcare": "Local tip: the nearby civil hospital holds a weekly disability-certificate camp.",
    "financial": "Local tip: the college scholarship cell helps students fill NSP forms.",
}
_EXPERT_NOTES = {
    "legal": (
        "Expert note: for wage disputes, complain to the local Labour Commissioner "
        "under the Minimum Wages Act; for a driving licence, apply at the RTO via "
        "parivahan.gov.in. Free legal aid is available at the District Legal "
        "Services Authority (DLSA)."
    ),
    "healthcare": (
        "Expert note: for a child with autism, get the UDID disability certificate "
        "from a government hospital's disability board — it unlocks the Niramaya "
        "health-insurance scheme and school accommodations under the RPwD Act."
    ),
    "financial": (
        "Expert note: apply for scholarships on the National Scholarship Portal "
        "(nsp.gov.in); most schemes need an income certificate and marksheets, and "
        "there are dedicated schemes for low-income and first-generation students."
    ),
}


async def simulate_enrichment() -> None:
    """Human-in-the-loop enrichment across ALL THREE expert domains.

    For each of legal / healthcare / financial: a local volunteer (Gaurav) adds
    a local tip to a pending Q&A, then that domain's expert (Hema / Anjali /
    Rakesh) enriches and approves it — chunking + embedding it into `documents`
    (Stream 2). Uses the accounts from seed_reviewers.py.
    """
    import crud.dashboard_user as crud_du
    import crud.expert as crud_expert
    import crud.qa_review as crud_qa
    import crud.volunteer as crud_volunteer
    from services.knowledge.ingest import ingest_qa_review

    print(f"\n{_RULE}\n  ENRICHMENT LOOP — volunteer + experts (legal / healthcare / financial)\n{_RULE}")

    vol_user = await crud_du.get_by_email(VOLUNTEER_EMAIL)
    vol = await crud_volunteer.get_by_user_id(vol_user.id) if vol_user else None
    if vol is None:
        print("  (volunteer account not found — run scripts/seed_reviewers.py)")

    for domain in ("legal", "healthcare", "financial"):
        pending = await crud_qa.list_pending(domain=domain, limit=1)
        if not pending:
            print(f"\n  [{domain}] no pending Q&A — run the WhatsApp sim first.")
            continue
        review = pending[0]
        print(f"\n  [{domain}] Q: {review.user_question[:60]}…")

        if vol is not None:
            await crud_qa.set_local_input(review.id, _LOCAL_TIPS[domain], vol.id)
            print(f"    ✍️  Volunteer ({vol.name}) added local input.")

        experts = await crud_expert.list_for_domain(domain, limit=1)
        if not experts:
            print(f"    (no {domain} expert seeded — run scripts/seed_reviewers.py)")
            continue
        expert = experts[0]
        await crud_qa.set_expert_input(review.id, _EXPERT_NOTES[domain], expert.id)
        chunk_id = await ingest_qa_review(review.id, expert.id)
        print(f"    ✅  Expert ({expert.name}) approved + ingested → chunk {chunk_id}")


async def _amain(args: argparse.Namespace) -> None:
    workflow = await compile_router()
    try:
        if not args.no_whatsapp:
            personas = WHATSAPP_PERSONAS
            if args.persona:
                personas = [p for p in WHATSAPP_PERSONAS if p.key == args.persona]
                if not personas:
                    keys = ", ".join(p.key for p in WHATSAPP_PERSONAS)
                    print(f"Unknown persona '{args.persona}'. Choose from: {keys}")
                    return
            for persona in personas:
                await simulate_persona(
                    workflow, persona, reset=args.reset, use_llm=args.llm
                )
        if args.enrich:
            await simulate_enrichment()
    finally:
        from config.db import close_checkpointer

        await close_checkpointer()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 1-week persona simulation.")
    parser.add_argument(
        "--persona", help="run a single persona (jyotsana | manisha | gaurav | mohan)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="wipe each persona's prior data first (fresh onboarding + memory)",
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="also run the volunteer + expert (Hema) enrichment loop",
    )
    parser.add_argument(
        "--no-whatsapp",
        action="store_true",
        help="skip the WhatsApp personas (e.g. to run only --enrich)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="generate each persona's messages with an LLM (in-character, in "
        "their language) instead of sending the scripted text verbatim",
    )
    asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    main()
