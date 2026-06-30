"""Pending Reviews page — qa_reviews list with local_input form (volunteers).

Volunteers see all pending reviews (filtered by domain); experts see only
their domain's. Both can attach `local_input` to enrich the answer that
the expert will eventually approve.

The expert's own enrichment form lives on the Approvals page.
"""

from __future__ import annotations

import streamlit as st

import crud.qa_review as crud_qa_review
import crud.volunteer as crud_volunteer
from services.dashboard.auth import Role, require_login
from services.dashboard.db import run_async

DOMAIN_OPTIONS = ["legal", "medical", "financial"]


def _volunteer_id_for(user_id: str):
    """Look up the volunteer's profile row by their login user_id."""
    from uuid import UUID

    return run_async(crud_volunteer.get_by_user_id(UUID(user_id)))


def main() -> None:
    user = require_login()

    st.title("📥 Pending Reviews")
    st.caption(
        "Open Q&A pairs the bot sent out. Volunteers add local context; "
        "experts enrich and approve on the next page."
    )

    domain_filter = st.selectbox(
        "Domain",
        options=["(all)"] + DOMAIN_OPTIONS,
        index=0,
    )

    pending = run_async(
        crud_qa_review.list_pending(
            domain=None if domain_filter == "(all)" else domain_filter,
            limit=50,
        )
    )
    if not pending:
        st.info("No pending reviews 🎉")
        return

    for review in pending:
        with st.expander(
            f"[{review.domain}] {review.user_question[:80]}…  •  {review.created_at:%Y-%m-%d %H:%M}",
            expanded=False,
        ):
            st.markdown("**User's question**")
            st.write(review.user_question)
            st.markdown("**Bot's answer**")
            st.write(review.bot_answer)

            st.divider()
            st.markdown("**Volunteer local input** (optional)")
            local_input_default = review.local_input or ""
            local_input = st.text_area(
                "Add local context",
                value=local_input_default,
                key=f"local_input_{review.id}",
                placeholder="e.g. 'In Maharashtra, the relevant statute is X'",
            )
            if st.button(
                "Save local input",
                key=f"save_local_{review.id}",
                disabled=(local_input == local_input_default),
            ):
                # Look up volunteer profile; skip if the user isn't a volunteer.
                vol = _volunteer_id_for(user.user_id)
                if vol is None and user.role == "volunteer":
                    st.error("Your login isn't linked to a volunteer profile yet — ask an admin.")
                    st.stop()
                volunteer_id = vol.id if vol is not None else None
                run_async(
                    crud_qa_review.set_local_input(
                        review.id, local_input.strip(), volunteer_id
                    )
                )
                st.success("Local input saved.")
                st.rerun()


main()