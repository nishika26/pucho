"""FastAPI entrypoint for the Pucho WhatsApp webhook.

Routes:
    POST /whatsapp/webhook   — Twilio WhatsApp inbound messages
    GET  /healthz            — liveness probe (used by Vercel warm-up checks)

The handler:
  1. Verifies the X-Twilio-Signature header (HMAC-SHA1 of the full URL +
     sorted form params, keyed by the Twilio auth token). 403 on mismatch.
  2. Translates the Twilio form into a Pucho router state.
  3. Awaits the router graph (STT → classify → domain agent → TTS).
  4. Returns TwiML with either a <Body> or <Media> element.

Lifespan:
  On startup: builds + compiles the LangGraph router with its
  AsyncPostgresSaver checkpointer (short-term memory). On shutdown:
  closes the checkpointer.

Vercel uses `whatsapp/main.py` as the @vercel/python builder source (see
vercel.json). Local dev runs `uv run main.py`, which spins up uvicorn on
this same `app`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from twilio.request_validator import RequestValidator

from api.routes.whatsapp.adapter import twilio_form_to_state_and_context
from config.db import close_checkpointer
from config.settings import settings
from services.agent import compile_router, make_thread_id

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Compile the router (with PostgresSaver) at startup; close on shutdown."""
    # Store the compiled graph on app.state. Importing `router_workflow` by
    # name would capture the None bound at import time and never see the
    # post-compile reassignment, so we read it off app.state per request.
    app.state.router_workflow = await compile_router()
    try:
        yield
    finally:
        await close_checkpointer()


app = FastAPI(title="Pucho WhatsApp Webhook", lifespan=lifespan)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    auth_token = settings.TWILIO_AUTH_TOKEN
    if not auth_token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")

    form = await request.form()
    form_dict = {key: value for key, value in form.items()}

    # Signature validation is HMAC'd over the exact public URL Twilio called.
    # Behind a local tunnel (ngrok) the proxied scheme/host differ from what
    # uvicorn reconstructs, so we only enforce it in production.
    if x_twilio_signature and settings.ENVIRONMENT == "production":
        validator = RequestValidator(auth_token)
        full_url = str(request.url)
        if not validator.validate(full_url, form_dict, x_twilio_signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    router_workflow = getattr(request.app.state, "router_workflow", None)
    if router_workflow is None:
        raise HTTPException(status_code=503, detail="Router not initialised")

    # Twilio drops the webhook after 15s, but our pipeline (STT + LLMs + TTS)
    # routinely takes longer. So we ACK immediately with an empty TwiML and do
    # the work in the background, then push the reply via the REST API. This is
    # Twilio's recommended pattern for slow handlers.
    asyncio.create_task(_process_and_reply(router_workflow, form_dict))
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml",
    )


async def _process_and_reply(router_workflow, form_dict: dict) -> None:
    """Run the graph and send the reply out-of-band (not blocking the webhook)."""
    try:
        state, context = await twilio_form_to_state_and_context(form_dict)
        thread_id = make_thread_id(context.phone_number)
        final_state = await router_workflow.ainvoke(
            state,
            context=context,
            config={"configurable": {"thread_id": thread_id}},
        )
        text = (final_state.get("output_text") or "").strip()
        media_url = final_state.get("output_audio_url")
        await _send_whatsapp(context.phone_number, text, media_url)
    except Exception:
        log.exception("background webhook processing failed")


async def _send_whatsapp(phone: str, text: str, media_url: str | None) -> None:
    """Send the reply via Twilio's REST API (text + audio as separate messages)."""
    from twilio.rest import Client

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    from_ = settings.TWILIO_WHATSAPP_NUMBER  # e.g. "whatsapp:+14155238886"
    to = f"whatsapp:{phone}"

    def _send() -> None:
        # WhatsApp audio can't carry a caption, so text and audio go separately.
        if text:
            client.messages.create(from_=from_, to=to, body=text)
        if media_url:
            client.messages.create(from_=from_, to=to, media_url=[media_url])

    await asyncio.to_thread(_send)
