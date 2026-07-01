"""Upload TTS audio bytes to Vercel Blob and return the public URL.

Twilio's webhook reply can carry audio via the `<Media>` TwiML element, but
the URL must be publicly reachable. Vercel Blob is the lowest-friction option
for a project already deploying to Vercel — no extra IAM, no bucket policy.
"""

from __future__ import annotations

import logging
import uuid

import vercel_blob

from services.tools.text_to_speech import text_to_speech


async def upload_audio(audio_bytes: bytes, *, filename: str | None = None) -> str:
    """Upload `audio_bytes` to Vercel Blob and return its public URL.

    Raises:
        RuntimeError: if `BLOB_READ_WRITE_TOKEN` is not configured.
        vercel_blob.VercelBlobError: on upload failure (propagated).
    """
    from config.settings import settings

    token = settings.BLOB_READ_WRITE_TOKEN
    if not token:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN is not set — Vercel Blob uploads require it. "
            "Get one from the Vercel dashboard (Storage → Blob) and add it to "
            "your project's environment variables."
        )

    name = filename or f"pucho-tts/{uuid.uuid4().hex}.wav"
    # vercel_blob.put(path, data, options) — the token goes inside the options
    # dict (not a kwarg); the store is public by default.
    result = vercel_blob.put(name, audio_bytes, {"token": token})
    return result["url"]


async def synthesize_and_upload(
    text: str,
    *,
    language: str,
    prefix: str,
) -> str | None:
    """Run TTS on `text`, upload to Vercel Blob, return the public URL.

    Domain agents call this when the user's modality is voice. Best-effort:
    if TTS or the upload fails (missing Blob token, Sarvam error, etc.), we
    log and return None so the caller replies with TEXT instead of 500-ing —
    a voice user always gets *an* answer.
    """
    try:
        audio_bytes: bytes = await text_to_speech.ainvoke(
            {"text": text, "target_language_code": language}
        )
        # .mp3 so Vercel Blob serves it as audio/mpeg (WhatsApp-playable).
        filename = f"pucho-tts/{prefix}-{uuid.uuid4().hex}.mp3"
        return await upload_audio(audio_bytes, filename=filename)
    except Exception:
        logging.getLogger(__name__).exception(
            "TTS/upload failed; falling back to a text reply"
        )
        return None
