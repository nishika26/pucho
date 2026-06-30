"""User Memory page — browse + delete long-term memory facts per user.

Experts see only their domain's memories; admins see everything. Volunteers
can't see memories (they're internal to the bot's reasoning; surfacing them
would create a privacy concern).
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

import crud.expert as crud_expert
import crud.memory as crud_memory
import crud.user as crud_user
from models.memory import MemoryDomain
from services.dashboard.auth import require_role
from services.dashboard.db import run_async

DOMAIN_OPTIONS = ["legal", "medical", "financial"]


def _list_users_with_memories():
    """Lightweight list of users who have at least one memory row."""
    from sqlalchemy import text
    from services.dashboard.db import session_scope

    with session_scope() as session:
        result = session.exec(
            text(
                "SELECT DISTINCT u.id, u.phone_number, u.email, u.display_name "
                "FROM users u JOIN user_memories m ON m.user_id = u.id "
                "ORDER BY u.created_at DESC LIMIT 200"
            )
        )
        return [dict(r._mapping) for r in result.all()]


def main() -> None:
    user = require_role("expert", "admin")

    st.title("🧠 User Memory")
    st.caption(
        "Long-term facts the bot has learned about each user. "
        "Expert access is scoped to their domain; admins see all."
    )

    users = _list_users_with_memories()
    if not users:
        st.info("No memory rows yet.")
        return

    label_options = [
        f"{u.get('display_name') or u.get('email') or u.get('phone_number') or u['id']}  •  {u['id']}"
        for u in users
    ]
    selected = st.selectbox("User", options=label_options)
    if not selected:
        return
    selected_user_id = UUID(selected.split("•")[-1].strip())

    if user.role == "expert":
        from uuid import UUID as _UUID
        expert_rows = run_async(crud_expert.list_for_user(_UUID(user.user_id)))
        allowed_domains = {e.domain for e in expert_rows}
        domain_filter = st.selectbox(
            "Domain",
            options=[d for d in DOMAIN_OPTIONS if d in allowed_domains],
        )
        if not domain_filter:
            st.error("You're not registered as an expert for any domain.")
            st.stop()
    else:
        domain_filter = st.selectbox("Domain", options=DOMAIN_OPTIONS, index=0)

    memories = run_async(
        crud_memory.list_for_user_domain(
            selected_user_id, MemoryDomain(domain_filter), limit=200
        )
    )
    if not memories:
        st.info(f"No `{domain_filter}` memories for this user.")
        return

    for mem in memories:
        with st.expander(
            f"{mem.domain}.{mem.key}  •  conf={mem.confidence:.2f}  •  updated {mem.updated_at:%Y-%m-%d %H:%M}",
            expanded=False,
        ):
            st.json(mem.value)
            st.caption(f"source_message_id: `{mem.source_message_id}`")
            st.caption(f"id: `{mem.id}`")
            if st.button("🗑️ Delete", key=f"del_mem_{mem.id}"):
                run_async(crud_memory.delete(selected_user_id, mem.domain, mem.key))
                st.success("Deleted.")
                st.rerun()


main()