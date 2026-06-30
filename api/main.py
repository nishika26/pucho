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

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from twilio.request_validator import RequestValidator

from api.routes.whatsapp.adapter import (
    build_twiml_reply,
    twilio_form_to_state_and_context,
)
from config.db import close_checkpointer
from services.agents import compile_router, make_thread_id, router_workflow


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Compile the router (with PostgresSaver) at startup; close on shutdown."""
    await compile_router()
    try:
        yield
    finally:
        await close_checkpointer()


app = FastAPI(title="Pucho WhatsApp Webhook", lifespan=lifespan)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> str:
    return "ok"


@app.post("/whatsapp/webhook", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> str:
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not auth_token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is not configured")

    form = await request.form()
    form_dict = {key: value for key, value in form.items()}

    if x_twilio_signature:
        validator = RequestValidator(auth_token)
        # Use the full URL Twilio actually called, unmodified.
        full_url = str(request.url)
        if not validator.validate(full_url, form_dict, x_twilio_signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    if router_workflow is None:
        # Defensive: lifespan should have compiled the graph before any request
        # arrives. If it didn't, the PostgresSaver probably couldn't init
        # (bad DSN, missing pg, etc.) — surface as a 503.
        raise HTTPException(status_code=503, detail="Router not initialised")

    state, context = await twilio_form_to_state_and_context(form_dict)
    # thread_id is the same `wa-{phone}` string used by the messages table,
    # so the PostgresSaver scopes per-thread state per WhatsApp sender.
    thread_id = make_thread_id(context.phone_number)
    final_state = await router_workflow.ainvoke(
        state,
        context=context,
        config={"configurable": {"thread_id": thread_id}},
    )

    text = final_state.get("output_text") or ""
    media_url = final_state.get("output_audio_url")
    return build_twiml_reply(text, media_url)
