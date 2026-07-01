"""Local Volunteer page.

A local volunteer sees the pending Q&A pairs the bot produced and adds their
own local context in the `local_input` column. Experts later read this input,
add their own, and approve.
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

import crud.qa_review as crud_qa_review
import crud.volunteer as crud_volunteer
from services.dashboard.auth import require_role
from services.dashboard.db import run_async

DOMAIN_OPTIONS = ["legal", "healthcare", "financial"]


def main() -> None:
    # Experts + admins can also view the volunteer page (not the other way).
    user = require_role("local_volunteer", "expert", "admin")

    st.title("🙋 Local Volunteer")
    st.caption(
        "Open Q&A pairs the bot sent out. Add local context an expert can use "
        "when enriching and approving the answer."
    )

    domain_filter = st.selectbox("Domain", options=["(all)"] + DOMAIN_OPTIONS, index=0)

    pending = run_async(
        crud_qa_review.list_pending(
            domain=None if domain_filter == "(all)" else domain_filter,
            limit=50,
        )
    )
    if not pending:
        st.info("No pending reviews 🎉")
        return

    # The volunteer's profile row (FK target for local_volunteer_id). Admins
    # may not have one — local_input is still saved, just without attribution.
    volunteer = (
        run_async(crud_volunteer.get_by_user_id(UUID(user.user_id)))
        if user.role == "local_volunteer"
        else None
    )
    if user.role == "local_volunteer" and volunteer is None:
        st.error(
            "Your login isn't linked to a volunteer profile yet — ask an admin."
        )
        st.stop()

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
            st.markdown("**Your local input**")
            default = review.local_input or ""
            local_input = st.text_area(
                "Add local context",
                value=default,
                key=f"local_input_{review.id}",
                placeholder="e.g. 'In Maharashtra, the relevant statute is X'",
            )
            if st.button(
                "Save local input",
                key=f"save_local_{review.id}",
                disabled=(local_input == default),
            ):
                run_async(
                    crud_qa_review.set_local_input(
                        review.id,
                        local_input.strip(),
                        volunteer.id if volunteer else None,
                    )
                )
                st.success("Local input saved.")
                st.rerun()


main()
