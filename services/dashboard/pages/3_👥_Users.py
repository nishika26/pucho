"""Users page — admin-only view of dashboard reviewers and bot users.

Admins can:
- List all dashboard users (volunteer / expert / admin) and reset their passwords.
- List WhatsApp senders (role IS NULL) and assign them a role (rare; mostly
  debugging).
- Create a new volunteer or expert (creates a `users` row + the matching
  profile row, with a generated initial password).
"""

from __future__ import annotations

import secrets
import string
from uuid import UUID

import streamlit as st

import crud.expert as crud_expert
import crud.user as crud_user
import crud.volunteer as crud_volunteer
from models.enums import ReviewerRole
from services.dashboard.auth import require_role
from services.dashboard.db import run_async

ROLE_OPTIONS = ["volunteer", "expert", "admin"]


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _list_users_by_role(role: str):
    return run_async(crud_user.list_for_role(role, limit=200))


def _list_whatsapp_senders():
    """Users with role=NULL. We don't have a CRUD helper for that yet —
    fall back to a SQL query via SQLModel's text().
    """
    from sqlalchemy import text
    from services.dashboard.db import session_scope

    with session_scope() as session:
        result = session.exec(
            text(
                "SELECT id, phone_number, display_name, preferred_language, "
                "       onboarded, created_at "
                "FROM users WHERE role IS NULL "
                "ORDER BY created_at DESC LIMIT 200"
            )
        )
        return [dict(r._mapping) for r in result.all()]


def main() -> None:
    require_role("admin")

    st.title("👥 Users")
    tab_reviewers, tab_senders, tab_create = st.tabs(
        ["Reviewers", "WhatsApp senders", "Create reviewer"]
    )

    with tab_reviewers:
        st.subheader("Dashboard reviewers")
        role_choice = st.selectbox("Role", ROLE_OPTIONS, index=0, key="rev_role")
        users = _list_users_by_role(role_choice)
        if not users:
            st.info(f"No users with role={role_choice}")
            return

        for u in users:
            with st.expander(f"{u.email}  •  {u.display_name or '—'}", expanded=False):
                st.write(
                    {
                        "id": str(u.id),
                        "email": u.email,
                        "display_name": u.display_name,
                        "role": u.role,
                        "last_login_at": u.last_login_at,
                        "created_at": u.created_at,
                    }
                )
                st.divider()
                with st.form(f"reset_pw_{u.id}"):
                    new_password = st.text_input("New password", type="password")
                    submitted = st.form_submit_button("Reset password")
                if submitted and new_password:
                    run_async(crud_user.set_password(u.id, new_password))
                    st.success("Password updated.")
                if role_choice == "volunteer":
                    vol = run_async(crud_volunteer.get_by_user_id(u.id))
                    st.write("Volunteer profile:", vol)
                elif role_choice == "expert":
                    experts = run_async(crud_expert.list_for_user(u.id))
                    if experts:
                        st.write("Expert domains:", [e.domain for e in experts])
                    else:
                        st.warning("No expert profile yet.")

    with tab_senders:
        st.subheader("WhatsApp senders (role IS NULL)")
        senders = _list_whatsapp_senders()
        st.write(f"{len(senders)} sender(s)")
        st.dataframe(senders, use_container_width=True)

    with tab_create:
        st.subheader("Create a new reviewer")
        with st.form("create_reviewer"):
            email = st.text_input("Email")
            display_name = st.text_input("Display name (optional)")
            role = st.selectbox("Role", ROLE_OPTIONS, index=0)
            domain = (
                st.selectbox("Expert domain", ["legal", "medical", "financial"])
                if role == "expert"
                else None
            )
            submitted = st.form_submit_button("Create")

        if submitted and email:
            initial_pw = _random_password()
            new_user = run_async(
                crud_user.create_with_email(
                    email=email.strip().lower(),
                    password=initial_pw,
                    role=role,
                    display_name=display_name or None,
                )
            )
            if role == "volunteer":
                run_async(
                    crud_volunteer.create(
                        user_id=new_user.id,
                        display_name=display_name or email,
                    )
                )
            elif role == "expert" and domain:
                run_async(
                    crud_expert.create(
                        user_id=new_user.id,
                        domain=domain,
                        display_name=display_name or email,
                    )
                )
            st.success(f"Created `{email}` (role={role}).")
            st.code(f"Initial password: {initial_pw}", language="text")
            st.warning("Copy this now — it won't be shown again.")


main()