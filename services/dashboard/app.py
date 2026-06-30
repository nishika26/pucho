"""Pucho ops dashboard (Streamlit).

Single-page entrypoint; the `pages/` directory hosts additional pages
that Streamlit auto-mounts in the sidebar.

Run locally:
    uv run streamlit run services/dashboard/app.py

Deploy:
    Streamlit Community Cloud points at `services/dashboard/app.py` and
    pulls secrets from its secrets manager (POSTGRES_*, OPENAI_API_KEY).
    See README.md in this directory.
"""

from __future__ import annotations

import streamlit as st

from services.dashboard.auth import (
    render_login_form,
    render_sidebar_user_info,
    require_login,
)

st.set_page_config(
    page_title="Pucho Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    user = st.session_state.get("user")
    if user is None:
        render_login_form()
        return

    require_login()  # raises st.stop() if not logged in (defensive)
    render_sidebar_user_info()

    st.title("🤖 Pucho Dashboard")
    st.markdown(
        """
        Use the sidebar to navigate:
        - **📥 Pending Reviews** — open QA reviews waiting on volunteer/expert input
        - **✅ Approvals** — experts approve + ingest approved Q&As into the knowledge base
        - **👥 Users** — admin view of dashboard reviewers and WhatsApp senders
        - **🧠 User Memory** — browse and edit long-term memory facts per user
        - **💬 Conversations** — read past WhatsApp transcripts per sender
        """
    )
    st.info(
        f"You are signed in as **{user.display_name or user.email}** "
        f"with role `{user.role}`."
    )


main()