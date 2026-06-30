"""Upload TTS audio bytes to Vercel Blob and return the public URL.

Twilio's webhook reply can carry audio via the `<Media>` TwiML element, but
the URL must be publicly reachable. Vercel Blob is the lowest-friction option
for a project already deploying to Vercel — no extra IAM, no bucket policy.
"""

from __future__ import annotations

import os
import uuid

import vercel_blob

from services.tools.text_to_speech import text_to_speech


async def upload_audio(audio_bytes: bytes, *, filename: str | None = None) -> str:
    """Upload `audio_bytes` to Vercel Blob and return its public URL.

    Raises:
        RuntimeError: if `BLOB_READ_WRITE_TOKEN` is not configured.
        vercel_blob.VercelBlobError: on upload failure (propagated).
    """
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN is not set — Vercel Blob uploads require it. "
            "Get one from the Vercel dashboard (Storage → Blob) and add it to "
            "your project's environment variables."
        )

    name = filename or f"pucho-tts/{uuid.uuid4().hex}.wav"
    result = vercel_blob.put(name, audio_bytes, token=token, access="public")
    return result["url"]


async def synthesize_and_upload(
    text: str,
    *,
    language: str,
    prefix: str,
) -> str:
    """Run TTS on `text`, upload to Vercel Blob, return the public URL.

    Domain agents call this when the user's modality is voice. The whole
    "synthesize audio → upload → return URL" sequence lives here so each
    domain agent doesn't have to duplicate it.
    """
    audio_bytes: bytes = await text_to_speech.ainvoke(
        {"text": text, "target_language_code": language}
    )
    filename = f"pucho-tts/{prefix}-{uuid.uuid4().hex}.wav"
    return await upload_audio(audio_bytes, filename=filename)
