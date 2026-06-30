"""Dashboard package — Streamlit entrypoint + auth + pages.

Layout (mirrors the senior-engineer doc's "human-in-the-loop" flow):
    app.py              — login gate, sidebar, page index
    auth.py             — bcrypt verify, session_user, role gates
    db.py               — sync engine + run_async bridge to async CRUD
    pages/
        1_📥_Pending_Reviews.py    — qa_reviews list + local_input form
        2_✅_Approvals.py           — expert-only approve + ingest
        3_👥_Users.py               — admin: list reviewers, password reset
        4_🧠_User_Memory.py         — long-term memory inspector + delete
        5_💬_Conversations.py       — transcript viewer + checkpoint peek
"""