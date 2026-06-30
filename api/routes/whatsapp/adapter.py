"""Translate between Twilio webhook payloads and the Pucho router state.

Twilio sends WhatsApp inbound messages as `application/x-www-form-urlencoded`.
Relevant fields:

    From        str   — the sender's WhatsApp number (e.g. "whatsapp:+91...")
    Body        str   — text body (empty when the message is media-only)
    NumMedia    str   — count of attached media items, as a string
    MediaUrl0   str   — URL of the first media item (authenticated)
    MediaContentType0  str  — MIME type of the first media item
    ProfileName str   — the WhatsApp profile name (best-effort)

The router graph expects a state dict with: `input_question`, `language`,
`modality`, (optional) `audio_bytes`, and an `AINVOKE context` carrying the
sender's `user_id`. This module builds both, persisting a `users` row and
an inbound `messages` row on the way in.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from api.routes.whatsapp.audio import upload_audio
from crud.message import create_message as create_message_row
from crud.user import get_or_create_by_phone
from services.agents.router import RouterContext, State

TWILIO_AUTH_USERNAME = os.environ.get("TWILIO_ACCOUNT_SID", "")


def _is_voice_note(content_type: str | None, body: str | None) -> bool:
    """Heuristic: Twilio delivers WhatsApp voice notes as audio/ogg or audio/opus."""
    if not content_type:
        return False
    ct = content_type.lower()
    return ct.startswith("audio/")


def _strip_whatsapp_prefix(raw: str) -> str:
    """Twilio prefixes sender numbers with "whatsapp:" — strip it for storage."""
    if raw.startswith("whatsapp:"):
        return raw[len("whatsapp:"):]
    return raw


async def _download_voice_bytes(media_url: str) -> bytes:
    async with httpx.AsyncClient(
        auth=(TWILIO_AUTH_USERNAME, os.environ["TWILIO_AUTH_TOKEN"])
    ) as client:
        resp = await client.get(media_url)
        resp.raise_for_status()
        return resp.content


async def twilio_form_to_state_and_context(
    form: dict[str, str],
) -> tuple[State, RouterContext]:
    """Build (state, context) for `router_workflow.ainvoke(state, context=...)`.

    Side effects on success:
    - upserts a `users` row keyed off the sender's phone number;
    - inserts an inbound `messages` row whose id is carried via the context.
    """
    raw_from = form.get("From", "") or ""
    phone = _strip_whatsapp_prefix(raw_from)

    num_media = int(form.get("NumMedia", "0") or "0")
    body = form.get("Body", "") or ""
    content_type = form.get("MediaContentType0")
    media_url = form.get("MediaUrl0")

    user = await get_or_create_by_phone(phone)

    if num_media > 0 and media_url and _is_voice_note(content_type, body):
        audio_bytes = await _download_voice_bytes(media_url)
        state: State = {
            "input_question": "",
            "language": "en-IN",
            "modality": "voice",
            "audio_bytes": audio_bytes,
        }
        inbound = await create_message_row(
            user_id=user.id,
            thread_id=f"wa-{phone}",
            role="human",
            modality="voice",
            content="",  # voice message body — transcribed to text by the router
        )
    else:
        state = {
            "input_question": body,
            "language": "en-IN",
            "modality": "text",
            "audio_bytes": None,
        }
        inbound = await create_message_row(
            user_id=user.id,
            thread_id=f"wa-{phone}",
            role="human",
            modality="text",
            content=body,
        )

    context = RouterContext(
        user_id=user.id,
        phone_number=phone,
        inbound_message_id=inbound.id,
    )
    return state, context


def build_twiml_reply(text: str, media_url: str | None) -> str:
    """Return a TwiML <Response> body.

    Twilio renders the <Media> element by downloading the URL; the URL must
    therefore be public (Vercel Blob upload gives us that).
    """
    # Minimal XML escape for the body — Twilio expects raw XML, not JSON.
    safe_text = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    media_el = f"<Media>{media_url}</Media>" if media_url else ""
    body_el = f"<Body>{safe_text}</Body>" if safe_text else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{body_el}{media_el}</Message></Response>"
    )


async def maybe_upload_audio(state: dict[str, Any]) -> str | None:
    """If the domain agent emitted raw audio bytes (via the TTS tool), upload them.

    The domain agents currently only write `output_text`; a future revision
    can have them also write `output_audio_bytes` (raw WAV) which this helper
    turns into a public URL. For now this is a no-op unless those bytes
    exist in state.
    """
    audio_bytes: bytes | None = state.get("output_audio_bytes")
    if not audio_bytes:
        return None
    parsed = urlparse(state.get("output_audio_filename") or "pucho-tts.wav")
    return await upload_audio(audio_bytes, filename=parsed.path.lstrip("/"))