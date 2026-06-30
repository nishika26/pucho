"""Approvals page — experts review pending Q&As and approve + ingest.

Only experts (and admins) can see this page. Approving a Q&A kicks off
`services.knowledge.ingest.ingest_qa_review` which chunks + embeds the
combined bot_answer + expert_input and writes rows to `documents` with
source='expert_approved'.
"""

from __future__ import annotations

import streamlit as st

import crud.expert as crud_expert
import crud.qa_review as crud_qa_review
from services.dashboard.auth import require_role
from services.dashboard.db import run_async
from services.knowledge.ingest import ingest_qa_review, reject_qa_review

DOMAIN_OPTIONS = ["legal", "medical", "financial"]


def main() -> None:
    user = require_role("expert", "admin")

    st.title("✅ Approvals & Ingest")
    st.caption(
        "Approve a Q&A pair to chunk + embed it into the knowledge base, "
        "or reject it so it doesn't reappear in the queue."
    )

    # Experts are scoped to their domain(s). Admins can pick any domain.
    if user.role == "admin":
        domain_filter = st.selectbox("Domain", options=DOMAIN_OPTIONS, index=0)
    else:
        # Find the expert's domain (a user can in theory be an expert for
        # multiple domains — show them all stacked).
        from uuid import UUID

        experts = run_async(crud_expert.list_for_user(UUID(user.user_id)))
        if not experts:
            st.error(
                "Your login isn't linked to any domain_experts row yet — "
                "ask an admin to assign you a domain."
            )
            st.stop()
        domain_options = [e.domain for e in experts]
        domain_filter = st.selectbox("Your domains", options=domain_options)

    pending = run_async(
        crud_qa_review.list_pending(domain=domain_filter, limit=50)
    )
    if not pending:
        st.info("Nothing pending for this domain 🎉")
        return

    for review in pending:
        with st.expander(
            f"[{review.domain}] {review.user_question[:80]}…",
            expanded=False,
        ):
            st.markdown("**User's question**")
            st.write(review.user_question)
            st.markdown("**Bot's answer**")
            st.write(review.bot_answer)

            if review.local_input:
                st.markdown("**Volunteer local input**")
                st.info(review.local_input)

            st.divider()
            expert_input_default = review.expert_input or ""
            expert_input = st.text_area(
                "Expert enrichment (concatenated with bot answer before ingest)",
                value=expert_input_default,
                key=f"expert_input_{review.id}",
                placeholder="Add statute references, citations, or clarifications.",
                height=160,
            )
            cols = st.columns(3)
            with cols[0]:
                if st.button(
                    "💾 Save enrichment",
                    key=f"save_enrich_{review.id}",
                    disabled=(expert_input == expert_input_default),
                ):
                    # Save enrichment first (so on subsequent renders it's
                    # already there if the user changes their mind).
                    from uuid import UUID
                    expert_row = run_async(
                        crud_expert.get_for_user_domain(UUID(user.user_id), review.domain)
                    )
                    if expert_row is None and user.role == "expert":
                        st.error("You're not registered as an expert for this domain.")
                        st.stop()
                    run_async(
                        crud_qa_review.set_expert_input(
                            review.id,
                            expert_input.strip(),
                            expert_row.id if expert_row else None,
                        )
                    )
                    st.success("Saved.")
                    st.rerun()
            with cols[1]:
                if st.button(
                    "✅ Approve & ingest",
                    key=f"approve_{review.id}",
                    type="primary",
                ):
                    from uuid import UUID
                    expert_row = run_async(
                        crud_expert.get_for_user_domain(UUID(user.user_id), review.domain)
                    )
                    if expert_row is None and user.role == "expert":
                        st.error("You're not registered as an expert for this domain.")
                        st.stop()
                    expert_id = expert_row.id if expert_row else UUID(user.user_id)
                    try:
                        last_chunk_id = run_async(
                            ingest_qa_review(review.id, expert_id)
                        )
                    except Exception as e:
                        st.error(f"Ingest failed: {e}")
                        st.stop()
                    st.success(
                        f"Ingested into `documents`. Last chunk id: `{last_chunk_id}`."
                    )
                    st.rerun()
            with cols[2]:
                if st.button(
                    "❌ Reject",
                    key=f"reject_{review.id}",
                ):
                    from uuid import UUID
                    expert_row = run_async(
                        crud_expert.get_for_user_domain(UUID(user.user_id), review.domain)
                    )
                    expert_id = expert_row.id if expert_row else UUID(user.user_id)
                    run_async(reject_qa_review(review.id, expert_id))
                    st.success("Rejected.")
                    st.rerun()


main()