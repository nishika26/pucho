"""Voice-to-text tool (Sarvam AI).

Wraps the `sarvamai` SDK as a LangChain tool so the router agent can call it
when the inbound WhatsApp message has voice modality. The router passes the raw
audio bytes (already fetched from Twilio's MediaUrl0 by the WhatsApp adapter)
to this tool; the tool returns the transcribed text.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_core.tools import tool
from sarvamai import AsyncSarvamAI


@lru_cache(maxsize=1)
def _client() -> AsyncSarvamAI:
    api_key = os.environ.get("SARVAM_API_KEY")
    if not api_key:
        raise RuntimeError("SARVAM_API_KEY is not set")
    return AsyncSarvamAI(api_subscription_key=api_key)


@tool
async def speech_to_text(audio_bytes: bytes, language_code: str = "unknown") -> str:
    """Transcribe voice audio to text using Sarvam AI's saarika:v2 model.

    Args:
        audio_bytes: Raw audio bytes (e.g. WhatsApp voice-note ogg/opus decoded).
        language_code: BCP-47 language code, or "unknown" for auto-detect.

    Returns:
        The transcribed text.
    """
    response = await _client().speech_to_text.transcribe(
        file=audio_bytes,
        model="saarika:v2",
        language_code=language_code,
    )
    # The SDK returns a typed response with a `transcript` field.
    return response.transcript
