"""Expert page.

An expert sees the pending Q&A pairs (with any local-volunteer input), adds
their own `expert_input`, and decides whether to approve the answer. Approving
chunks + embeds bot_answer + expert_input into the `documents` knowledge base;
rejecting drops it from the queue.
"""

from __future__ import annotations

from uuid import UUID

import streamlit as st

import crud.expert as crud_expert
import crud.qa_review as crud_qa_review
from services.dashboard.auth import require_role
from services.dashboard.db import run_async
from services.knowledge.ingest import ingest_qa_review, reject_qa_review

DOMAIN_OPTIONS = ["legal", "healthcare", "financial"]


def main() -> None:
    user = require_role("expert", "admin")

    st.title("🧑‍⚖️ Expert")
    st.caption(
        "Review each Q&A pair, add your enrichment, and approve to ingest it "
        "into the knowledge base — or reject it."
    )

    # Experts are scoped to the domain(s) they're registered for; admins see all.
    if user.role == "admin":
        domain_filter = st.selectbox("Domain", options=DOMAIN_OPTIONS, index=0)
        expert_domains = set(DOMAIN_OPTIONS)
    else:
        experts = run_async(crud_expert.list_for_user(UUID(user.user_id)))
        if not experts:
            st.error(
                "Your login isn't linked to any domain_experts row yet — "
                "ask an admin to assign you a domain."
            )
            st.stop()
        expert_domains = {e.domain for e in experts}
        domain_filter = st.selectbox("Your domains", options=sorted(expert_domains))

    pending = run_async(crud_qa_review.list_pending(domain=domain_filter, limit=50))
    if not pending:
        st.info("Nothing pending for this domain 🎉")
        return

    def _expert_id_for(domain: str) -> UUID | None:
        row = run_async(crud_expert.get_for_user_domain(UUID(user.user_id), domain))
        return row.id if row else None

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
            default = review.expert_input or ""
            expert_input = st.text_area(
                "Your advice",
                value=default,
                key=f"expert_input_{review.id}",
                placeholder="Add statute references, citations, or clarifications.",
                height=160,
            )

            cols = st.columns(3)
            with cols[0]:
                if st.button(
                    "💾 Save input",
                    key=f"save_expert_{review.id}",
                    disabled=(expert_input == default),
                ):
                    expert_id = _expert_id_for(review.domain)
                    if expert_id is None and user.role == "expert":
                        st.error("You're not registered as an expert for this domain.")
                        st.stop()
                    run_async(
                        crud_qa_review.set_expert_input(
                            review.id, expert_input.strip(), expert_id
                        )
                    )
                    st.success("Saved.")
                    st.rerun()
            with cols[1]:
                if st.button("✅ Approve", key=f"approve_{review.id}", type="primary"):
                    expert_id = _expert_id_for(review.domain)
                    if expert_id is None and user.role == "expert":
                        st.error("You're not registered as an expert for this domain.")
                        st.stop()
                    # Persist the latest enrichment before ingest.
                    if expert_input.strip() != default:
                        run_async(
                            crud_qa_review.set_expert_input(
                                review.id, expert_input.strip(), expert_id
                            )
                        )
                    try:
                        last_chunk_id = run_async(
                            ingest_qa_review(review.id, expert_id)
                        )
                    except Exception as e:  # noqa: BLE001 — surface to the UI
                        st.error(f"Ingest failed: {e}")
                        st.stop()
                    st.success(f"Approved + ingested. Last chunk id: `{last_chunk_id}`.")
                    st.rerun()
            with cols[2]:
                if st.button("❌ Reject", key=f"reject_{review.id}"):
                    expert_id = _expert_id_for(review.domain)
                    if expert_id is None and user.role == "expert":
                        st.error("You're not registered as an expert for this domain.")
                        st.stop()
                    run_async(reject_qa_review(review.id, expert_id))
                    st.success("Rejected.")
                    st.rerun()


main()
