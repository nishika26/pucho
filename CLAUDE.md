# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Pucho** is a **WhatsApp chatbot** built on LangChain + LangGraph. The intended pipeline:

1. WhatsApp message arrives (text or voice; **images are out of scope for v1**).
2. **Router agent** classifies the query into legal / medical / financial. If the input was voice, the router calls an **internal STT tool** to transcribe before classifying. STT lives **inside the router as a tool** — not as a pre-processing step.
3. Router hands off to the matching **domain agent** (legal / medical / financial).
4. The domain agent handles the query. If the user's original modality was voice, the agent calls its **internal TTS tool** to produce an audio reply. Text-in stays text-out.
5. The `whatsapp/` directory is the adapter layer — it converts incoming WhatsApp messages into the agent's input format and ships agent output back to the user.

State passed from router → domain agent carries: `input_question`, `language`, `modality` (`text` | `voice`).

### Provider choices (locked in for v1)

- **LLM:** OpenAI (`langchain-openai`, `ChatOpenAI`).
- **STT:** Sarvam AI via the `sarvamai` Python SDK (router tool).
- **TTS:** Sarvam AI via the `sarvamai` Python SDK (each domain agent's tool).
- **WhatsApp:** Twilio webhook, served by **FastAPI**. The `whatsapp/` directory hosts the webhook handler.
- **Deployment:** Vercel (`@vercel/python` hosting the FastAPI app).
- **RAG:** each domain agent has its **own** RAG (its own vector store / retriever / corpus). Do not share a single retriever across legal / medical / financial — the corpora and access boundaries differ.
- **Corpus is already collected** — only retrieval is in scope for v1; document ingest (chunking / embedding / upsert) is not.

### Vercel constraints to design around

Vercel serverless functions are stateless — **no persistent disk between invocations**. The vector store must therefore be hosted (not file-backed).

**Vector store: deferred to user choice.** Acceptable options: Pinecone, Qdrant Cloud, Weaviate Cloud, Upstash Vector, Neon/Supabase with pgvector, or Chroma in client/server mode. **Local ChromaDB and FAISS-on-disk are not viable on Vercel.**

**Architectural consequence:** the RAG layer in each domain agent sits behind a thin interface (a `Retriever` protocol or equivalent) so the vector store can be swapped without touching `legal.py` / `medical.py` / `financial.py`.

## Development Commands

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

- **Install dependencies**: `uv sync`
- **Run the app**: `uv run main.py` (currently just prints "Hello from pucho!")
- **Run a script in the project context**: `uv run python <script>.py`
- **Add a dependency**: `uv add <package>`
- **Pin Python version**: managed via `.python-version` (3.13)

There is no test suite, linter, or formatter configured yet. The `agents/__init__.py` exists but no tests/ directories.

## Architecture

```
pucho/
├── main.py                  # Entry point (placeholder)
├── pyproject.toml           # Project config, deps: langchain, langgraph
├── agents/                  # Domain agents + router
│   ├── __init__.py
│   ├── financial.py         # (empty stub — financial domain agent)
│   ├── legal.py             # (empty stub — legal domain agent)
│   ├── medical.py           # (empty stub — medical domain agent)
│   ├── summarier.py         # (empty stub — summarization agent)
│   └── router.py            # LangGraph router that classifies input → routes to a domain agent
├── dashboard/               # (empty — intended UI/dashboard surface)
└── whatsapp/                # (empty — intended WhatsApp integration surface)
```

### Router design (`agents/router.py`)

Built on LangGraph's `StateGraph`. The flow:

1. `START` → router node — reads `input_question`, `language`, `modality` from state. If `modality == "voice"`, it calls its internal **STT tool** to transcribe the voice input into text. Then it classifies the query into legal / medical / financial via a structured-output LLM call (`Route` schema, `Literal["financial", "legal", "medical"]`).
2. Conditional edge routes to the matching domain agent node.
3. Each domain agent handles the query. If `modality == "voice"`, it calls its internal **TTS tool** to produce an audio reply before writing to `output`. Text-in replies stay text.
4. Domain agent node → `END`.

State shape (`State` TypedDict): `{ input_question: str, language: str, modality: Literal["text", "voice"], decision: str, output: str }`.

**Design constraint:** STT and TTS are **tools inside agents**, not separate graph nodes. The router's tool list contains STT; each domain agent's tool list contains TTS.

### Known gaps in `agents/router.py`

The file references names that are **not yet imported/defined** and will fail to execute as-is:

- `llm` (used by `router = llm.with_structured_output(Route)` and each `llm_call_*`)
- `StateGraph`, `START`, `END` from `langgraph`
- `display`, `Image` from IPython (used for Mermaid graph rendering)

When filling these in, mirror the LangChain v1 / LangGraph v1 API surface (the project pins `langchain>=1.3.11` and `langgraph>=1.2.6`).

## Conventions

- Domain agents live as siblings in `agents/` and are re-exported via `agents/__init__.py`. New domains follow the same `agents/<domain>.py` pattern.
- The router imports them as `from agents import financial, legal, medical` — keep that namespace when adding modules.
- The `Route` Pydantic model and `Literal` union in `router.py` are the source of truth for which domains the router can dispatch to; update them together when adding a new domain.
- **STT and TTS are tools inside agents** — never separate graph nodes. Router holds STT; domain agents hold TTS.
- **Modality drives TTS:** `modality == "voice"` → invoke TTS tool; otherwise return text. Image modality is not in scope for v1.
- **Language flows in state**, not as a side channel — domain agents read `state["language"]` to localize replies.
- **Each domain agent owns its RAG** — separate retriever / vector store per domain (legal, medical, financial). Don't funnel all three through one shared retriever.
- **RAG goes behind a `Retriever` interface** — keeps the vector-store swap (when the user picks one) local to one module instead of touching the three domain agents.
