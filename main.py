"""Local development entrypoint.

Run with `uv run main.py` (or `uv run uvicorn api.main:app --reload`).
Vercel (if used) serves `api/main.py:app` via @vercel/python — see vercel.json.
"""

import os

import uvicorn

from api.main import app


def main() -> None:
    # Container hosts (Render / Railway / Fly) inject the port to bind via $PORT.
    # Fall back to 8000 for local dev.
    port = int(os.environ.get("PORT", "8000"))
    # proxy_headers + forwarded_allow_ips let uvicorn trust the host's TLS proxy
    # (X-Forwarded-Proto/Host), so request.url reconstructs as the real https URL
    # Twilio called — required for the webhook's signature validation to pass in
    # production behind Render.
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
