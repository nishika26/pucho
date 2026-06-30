"""Local development entrypoint.

Run with `uv run main.py` (or `uv run uvicorn whatsapp.main:app --reload`).
Vercel ignores this file and uses whatsapp/main.py via @vercel/python.
"""

import uvicorn

from api.main import app


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
