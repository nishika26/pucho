# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pucho** is a **WhatsApp helpline** (legal / healthcare / financial guidance for
India's urban poor) built on LangChain + LangGraph. The pipeline:

1. WhatsApp message arrives (text or voice; **images are out of scope for v1**).
2. The **LangGraph workflow** transcribes voice (Sarvam STT), onboards first-time
   users, then a **classify** node (one structured LLM call) picks the domain
   (legal / healthcare / financial) and profiles literacy + tone + an English
   `search_query`.
3. A conditional edge routes to the matching **domain handler** (`services/RAG/`).
4. The handler runs domain-scoped RAG (pgvector), injects the user's memory, and
   generates a grounded reply. If the original modality was voice, it synthesises
   audio (Sarvam TTS). Text-in stays text-out.
5. `api/routes/whatsapp/` is the adapter layer — it converts the Twilio webhook
   form into the workflow's input state and ships the reply back via Twilio's
   REST API.

State from classify → handler carries: `input_question`, `language`, `modality`
(`text` | `voice`), `decision`, `literacy_level`, `emotional_tone`, `search_query`.

### It is a workflow, NOT an agent — keep it honest

There is **no autonomous agent** here. An agent is an LLM that decides, in a loop,
which tool to call; Pucho has no such loop:

- **STT/TTS are deterministic tool calls**, gated on `modality` by a plain `if` in
  a graph node — the LLM never *selects* them. They are wrapped as LangChain tools
  for reuse, nothing more.
- **Routing is a single structured-output classification** (`Route` schema), not a
  tool loop. A hardcoded `if/elif` (`route_decision`) maps the label to a node.
- **Domain handlers use `create_agent(tools=[])`** — they retrieve once and
  generate. This is **classifier-routed static RAG**, not agentic RAG.

When describing the system, say "workflow" / "handler" — not "agent" / "multi-agent".

### Provider choices (locked in for v1)

- **LLM:** OpenAI (`langchain-openai`, `ChatOpenAI`, `gpt-4o-mini`).
- **STT:** Sarvam AI (`sarvamai` SDK) — called in the `transcribe_if_voice` node.
- **TTS:** Sarvam AI (`sarvamai` SDK) — called in each domain handler.
- **WhatsApp:** Twilio webhook served by **FastAPI** (`api/`). Because the full
  pipeline exceeds Twilio's 15s webhook timeout, the handler ACKs immediately and
  sends the reply out-of-band via the Twilio REST API.
- **RAG:** each domain has its **own** retriever / corpus (`services/RAG/` +
  `rag_corpus/<domain>/`). Do not share one retriever across domains.
- **Corpus is curated** — retrieval is in scope; there are also seed + expert
  ingest scripts (`scripts/seed_documents.py`, `services/knowledge/`).

### Vector store + persistence

Postgres + **pgvector** (Supabase). The vector store is hosted (not file-backed).
Short-term chat memory is LangGraph's `AsyncPostgresSaver` checkpointer (append-only
per `wa-<phone>` thread); long-term per-user facts live in `user_memories`. The RAG
layer sits behind a `Retriever` interface (`services/agent/retriever.py`,
implemented in `services/knowledge/retriever_impl.py`) so the store can be swapped
without touching the three domain handlers.

## Development Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

- **Install dependencies**: `uv sync`
- **Run the webhook app**: `uv run main.py` (FastAPI/uvicorn; binds `$PORT`, default `:8000`)
- **DB schema**: `uv run alembic upgrade head`
- **Seed corpus + reviewers**: `uv run python scripts/seed_documents.py` / `scripts/seed_reviewers.py`
- **Dashboard**: `PYTHONPATH=. uv run streamlit run services/dashboard/app.py`
- **1-week simulation**: `uv run python scripts/simulate.py --reset --enrich`
- **Add a dependency**: `uv add <package>`
- **Python**: 3.13 (`.python-version`)

No test suite / linter / formatter is configured yet.

## Deployment

The app is **container-based**, not serverless. The webhook ACKs Twilio instantly
and finishes the work (STT → LLM → RAG → TTS → reply) in a background task
(`asyncio.create_task` in `api/main.py`). That pattern needs a **long-running
process**, so:

- **Local / containers:** `Dockerfile` builds one image; `docker-compose.yml` runs
  both services (webhook + Streamlit dashboard) against the external Supabase DB.
- **Cloud (chosen): Render** via `render.yaml` (a Blueprint) — two `web` services
  (`pucho-webhook`, `pucho-dashboard`) from the same Dockerfile, sharing the
  `pucho-shared` secrets group. `main.py` binds Render's injected `$PORT` and sets
  `proxy_headers=True` so Twilio signature validation works behind Render's TLS proxy.
- **Vercel is NOT viable** despite `vercel.json` existing (now pointing at
  `api/main.py`). On serverless the function is frozen after the HTTP response, so
  the background task never sends the reply. Kept only as a reference; do not treat
  it as the deploy path.

Notes: Render free web services **spin down when idle** (cold-start can exceed
Twilio's 15s timeout — send a warm-up message first). Twilio signature checks run
only when `ENVIRONMENT == "production"`; if they 403 behind the proxy, set
`ENVIRONMENT=development` to skip them. Secrets are injected at runtime and are kept
out of the image via `.dockerignore` (never bake `.env`).

## Architecture

```
pucho/
├── main.py                  # Local dev entrypoint (uvicorn → api.main:app)
├── api/
│   ├── main.py              # FastAPI app: /whatsapp/webhook + /healthz
│   └── routes/whatsapp/     # Twilio adapter (form ↔ router state) + audio (TTS → Blob)
├── config/                  # settings (.env), async DB engine (db.py), checkpointer
├── models/                  # SQLModel tables + shared enums (8 tables)
├── crud/                    # async DB ops, one module per table
├── services/
│   ├── agent/               # router.py (StateGraph) + onboarding + retriever (interface) + style (prompt)
│   ├── RAG/                 # domain handlers: legal.py / healthcare.py / financial.py
│   ├── knowledge/           # corpus ingest + expert-approval enqueue + pgvector retriever impl
│   ├── memory/              # reflect (fact extraction) + inject (facts → prompt) + vocab
│   ├── tools/               # Sarvam STT / TTS
│   └── dashboard/           # Streamlit review app (auth + volunteer + expert views)
├── alembic/                 # migrations
├── rag_corpus/              # curated corpus (legal / healthcare / financial)
├── scripts/                 # seed_documents, seed_reviewers, simulate (+ personas)
├── Dockerfile               # single image for both services (webhook + dashboard)
├── docker-compose.yml       # local two-service run (webhook :8000 + dashboard :8501)
├── render.yaml              # Render Blueprint — the deploy path (see Deployment)
└── vercel.json              # points at api/main.py, but Vercel is NOT viable (see Deployment)
```

**Naming note.** The router + support modules are in `services/agent/` (singular);
the domain handlers are in `services/RAG/`. Imports use `from services.agent import
...` and `from services.RAG import legal, healthcare, financial`. A few older
docstrings still say `services/agents` (plural) — stale comments, not real paths.

### Router graph (`services/agent/router.py`)

A LangGraph `StateGraph` with an `AsyncPostgresSaver` checkpointer, compiled at
FastAPI startup (`compile_router()`). Node flow:

```
START → transcribe_if_voice → onboard →(conditional)→ classify
      →(conditional route_decision)→ legal_agent | healthcare_agent | financial_agent
      → persist_message → enqueue_review → reflect → END
```

- `transcribe_if_voice` — Sarvam STT **only if** `modality == "voice"`.
- `onboard` — first-contact welcome (captures name + locality), then short-circuits
  to END for that turn; passthrough once onboarded.
- `classify` — one `Route` structured-output call: `step` (domain) + `literacy_level`
  + `emotional_tone` + `search_query` (English, retrieval-only).
- domain node — `services/RAG/<domain>.run()`: retrieve → inject memory → generate →
  (optional) TTS.
- `persist_message` → `enqueue_review` (queue one `qa_reviews` row for the answering
  domain) → `reflect` (extract durable facts → `user_memories`, best-effort).

`State` is a `TypedDict`; `messages` uses the `add_messages` reducer so short-term
history accumulates across turns. Per-invocation `RouterContext` (user_id,
phone_number, onboarded, name) is passed via `ainvoke(..., context=...)`.

## Conventions

- The router + support modules live in `services/agent/`; the three domain handlers
  live in `services/RAG/` and are re-exported from `services/agent/__init__.py`. New
  domains follow the `services/RAG/<domain>.py` pattern.
- The `Route` model + `Literal` union in `router.py` and `route_decision` are the
  source of truth for dispatchable domains — update them together when adding a domain.
- **STT/TTS are deterministic, modality-gated tool calls** — never model-selected,
  never separate "agent" reasoning. Voice ⇒ invoke; text ⇒ skip.
- **Language flows in state**, not a side channel — handlers reply in the user's
  language; retrieval uses the English `search_query`.
- **Each domain owns its RAG** — separate retriever / corpus per domain. Don't funnel
  all three through one shared retriever.
- **RAG goes behind the `Retriever` interface** — keeps the vector-store swap local to
  `services/knowledge/retriever_impl.py`, not the handlers.
- **Personalisation** (`services/agent/style.py`) — one templated system prompt filled
  per turn from domain + literacy + tone + modality. Keep replies simple, jargon-free,
  and non-repetitive (no stock empathy lines).
