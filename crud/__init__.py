"""CRUD layer — async DB operations against the project tables.

Per the senior-engineer doc:
- All functions are `async def`.
- Return Pydantic/SQLModel models, not raw DB rows.
- Single responsibility — one function per operation.
- Never contains business logic.

Each submodule is per-table:
    crud.user    — get/insert/update on `users`
    crud.message — create/list on `messages`
    crud.memory  — upsert/list/delete on `user_memories`

Sessions are opened via `config.db.get_session()`.
"""