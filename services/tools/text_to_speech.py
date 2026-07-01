"""Text-to-voice tool (Sarvam AI).

Wraps the `sarvamai` SDK as a LangChain tool so each domain agent can call it
when the user's original modality was voice. Returns raw WAV bytes, which the
router graph uploads to Vercel Blob and exposes via Twilio's <Media> reply.
"""

from __future__ import annotations

import base64
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
async def text_to_speech(text: str, target_language_code: str) -> bytes:
    """Synthesize speech from text using Sarvam AI's bulbul:v2 model.

    Args:
        text: The text to speak.
        target_language_code: BCP-47 target language code (e.g. "en-IN",
            "hi-IN"). The domain agent picks this from state["language"].

    Returns:
        Raw MP3 bytes (audio/mpeg) — the format WhatsApp can play as media.
    """
    response = await _client().text_to_speech.convert(
        text=text,
        target_language_code=target_language_code,
        model="bulbul:v2",
        # MP3 so WhatsApp/Twilio accept the <Media> (it does NOT support WAV).
        output_audio_codec="mp3",
    )
    # Sarvam returns base64-encoded audio in `response.audios[0]`.
    return base64.b64decode(response.audios[0])
