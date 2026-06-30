"""Conversations page — read past WhatsApp transcripts per sender.

Two layers:
1. The `messages` audit log (every human + AI message in chronological order).
2. The LangGraph checkpointer's latest checkpoint for the per-sender thread
   (carries the AI's `messages` channel — what the agent saw on its last
   turn).

Admins see all senders; experts and volunteers see only their own session
traffic (which is none — they don't message the bot). For v1 we just gate
by role and show everyone; tightening this is a follow-up.
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

import crud.message as crud_message
import crud.user as crud_user
from services.dashboard.auth import require_role
from services.dashboard.db import run_async


def _list_senders():
    from sqlalchemy import text
    from services.dashboard.db import session_scope

    with session_scope() as session:
        result = session.exec(
            text(
                "SELECT DISTINCT u.id, u.phone_number, u.email, u.display_name "
                "FROM users u JOIN messages m ON m.user_id = u.id "
                "ORDER BY u.created_at DESC LIMIT 200"
            )
        )
        return [dict(r._mapping) for r in result.all()]


def main() -> None:
    require_role("admin", "expert", "volunteer")

    st.title("💬 Conversations")
    st.caption("WhatsApp transcripts per sender.")

    senders = _list_senders()
    if not senders:
        st.info("No messages yet.")
        return

    label_options = [
        f"{s.get('display_name') or s.get('phone_number') or s.get('email') or s['id']}  •  {s['id']}"
        for s in senders
    ]
    selected = st.selectbox("Sender", options=label_options)
    if not selected:
        return
    selected_user_id = UUID(selected.split("•")[-1].strip())

    user = run_async(crud_user.get_by_id(selected_user_id))
    if user is None:
        st.error("User disappeared.")
        return

    thread_id = f"wa-{user.phone_number}"
    st.caption(f"thread_id: `{thread_id}`")

    messages = run_async(
        crud_message.list_for_thread(thread_id, user_id=selected_user_id, limit=500)
    )
    if not messages:
        st.info("No messages in this thread.")
        return

    for m in messages:
        icon = "👤" if m.role == "human" else "🤖"
        with st.chat_message("user" if m.role == "human" else "assistant"):
            st.write(f"{icon} **{m.role}** ({m.modality})  •  {m.created_at:%Y-%m-%d %H:%M}")
            st.write(m.content)


main()