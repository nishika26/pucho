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

from typing import Any
from urllib.parse import urlparse

import httpx

from api.routes.whatsapp.audio import upload_audio
from config.settings import settings
from crud.message import create_message as create_message_row
from crud.whatsapp_user import get_or_create_by_whatsapp_number
from services.agent.router import RouterContext, State


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
    # Twilio media URLs require HTTP basic auth (account SID + auth token) and
    # then 307-redirect to a pre-signed CDN URL (mms.twiliocdn.com), so we must
    # follow redirects. httpx strips the auth header on the cross-host hop, which
    # is fine — the CDN URL is already signed.
    async with httpx.AsyncClient(
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        follow_redirects=True,
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

    user = await get_or_create_by_whatsapp_number(phone)

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

    # Seed the stored literacy profile (if any) so the classifier uses it as a
    # prior instead of starting cold each turn.
    if user.literacy_level is not None:
        state["literacy_level"] = user.literacy_level

    context = RouterContext(
        user_id=user.id,
        phone_number=phone,
        inbound_message_id=inbound.id,
        onboarded=user.onboarded,
        name=user.name,
    )
    return state, context


def build_twiml_reply(text: str, media_url: str | None) -> str:
    """Return a TwiML <Response> body.

    Text and audio go in SEPARATE <Message> elements: WhatsApp audio can't
    carry a caption, so combining a <Body> and an audio <Media> in one message
    gets rejected (nothing delivers). The public <Media> URL (Vercel Blob) is
    served as audio/mpeg so WhatsApp can play it.
    """
    # Minimal XML escape for the body — Twilio expects raw XML, not JSON.
    safe_text = (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    parts: list[str] = []
    if safe_text:
        parts.append(f"<Message><Body>{safe_text}</Body></Message>")
    if media_url:
        parts.append(f"<Message><Media>{media_url}</Media></Message>")
    if not parts:
        parts.append("<Message></Message>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{''.join(parts)}</Response>"
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