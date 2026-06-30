# Pucho Dashboard (Streamlit)

Run locally:

```bash
uv run streamlit run services/dashboard/app.py
```

The dashboard listens on `http://localhost:8501` by default.

## Pages

- **📥 Pending Reviews** — qa_reviews list; volunteers add `local_input`.
- **✅ Approvals** — experts approve + ingest (chunk + embed → `documents`).
- **👥 Users** — admin: list reviewers, password reset, role assignment.
- **🧠 User Memory** — long-term memory inspector (per-user, per-domain).
- **💬 Conversations** — WhatsApp transcript viewer.

## Roles

The dashboard reads `users.role` (set by admins via the Users page or the
`crud.user.create_with_email(...)` CRUD helper):

- `volunteer` — Pending Reviews only.
- `expert` — Pending Reviews + Approvals + User Memory (their domain only).
- `admin` — everything, plus the Users page.

## Deploy on Streamlit Community Cloud

1. Push the repo to GitHub.
2. Sign in to https://share.streamlit.io/ with the GitHub account.
3. New app → pick the repo → set main file path to `services/dashboard/app.py`.
4. Open **Advanced settings → Secrets** and paste:

   ```toml
   POSTGRES_SERVER = "aws-0-us-east-1.pooler.supabase.com"
   POSTGRES_USER   = "postgres.<project-ref>"
   POSTGRES_PASSWORD = "..."
   POSTGRES_DB     = "postgres"
   POSTGRES_PORT   = "6543"   # Supabase pooler (transaction mode) — not 5432
   OPENAI_API_KEY  = "sk-..."  # required by the Approvals page's ingest step
   ```

5. Deploy. First request runs `compile_router()` against the DB; the
   checkpointer's `setup()` is idempotent.

### Free-tier networking caveats

Streamlit Community Cloud (free tier) blocks outbound connections to most
non-whitelisted hosts. **Supabase's pooler (`*.pooler.supabase.com`) is
allowed**; raw Supabase IPv6 (port 5432) sometimes isn't. Use the pooler
host (port `6543` or `5432`) in `POSTGRES_SERVER`.

If you're not on Supabase, run the dashboard on Railway/Render/Fly instead —
both support arbitrary outbound.

## Migrations

The dashboard doesn't run migrations. Apply them once via:

```bash
POSTGRES_SERVER=... POSTGRES_USER=... alembic upgrade head
```

(from the repo root). The dashboard reads the resulting schema.

## Caveats

- The PostgresSaver checkpointer (used by the WhatsApp side) creates
  tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`) on first `setup()` — this happens automatically
  via FastAPI's lifespan when the webhook boots. You don't need to
  pre-create them; the dashboard doesn't touch them.
- Embeddings for the **Approvals** page are billed against your OpenAI
  account (`text-embedding-3-small`, 1536 dims).