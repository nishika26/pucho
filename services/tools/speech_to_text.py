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
    from config.settings import settings

    api_key = settings.SARVAMAI_API_KEY
    if not api_key:
        raise RuntimeError("SARVAMAI_API_KEY is not set")
    return AsyncSarvamAI(api_subscription_key=api_key)


@tool
async def speech_to_text(audio_bytes: bytes, language_code: str = "unknown") -> dict:
    """Transcribe voice audio to text using Sarvam AI's saarika:v2.5 model.

    Args:
        audio_bytes: Raw audio bytes (e.g. WhatsApp voice-note ogg/opus decoded).
        language_code: BCP-47 language code, or "unknown" for auto-detect.

    Returns:
        A dict with:
        - "transcript":    the transcribed text.
        - "language_code": the language Sarvam detected (e.g. "hi-IN"), so the
          caller can reply (and synthesize TTS) in the same language. May be
          None if the SDK didn't return one.
    """
    response = await _client().speech_to_text.transcribe(
        file=audio_bytes,
        model="saarika:v2.5",
        language_code=language_code,
    )
    # The SDK returns a typed response with `transcript` and (when
    # language_code="unknown") the detected `language_code`.
    return {
        "transcript": response.transcript,
        "language_code": getattr(response, "language_code", None),
    }
