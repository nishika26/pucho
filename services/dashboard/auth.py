"""Dashboard auth — login form + bcrypt verify.

The Streamlit script reruns top-to-bottom on each interaction; we use
`st.session_state` for any cross-rerun state (logged-in user_id, role).
There is no server-side session — Streamlit Community Cloud uses signed
cookies for the session ID, but the auth decision is local to the page
script.

The login gate is enforced by `require_login()` at the top of every page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import streamlit as st

import crud.dashboard_user as crud_user
from models.enums import DashboardRole

Role = Literal["local_volunteer", "expert", "admin"]


@dataclass(frozen=True)
class SessionUser:
    """Logged-in user info we keep in st.session_state."""

    user_id: str
    email: str
    role: Role
    display_name: str | None


def _set_session_user(user) -> None:
    st.session_state["user"] = SessionUser(
        user_id=str(user.id),
        email=user.email or "",
        role=user.role,
        display_name=user.name,
    )


def get_session_user() -> SessionUser | None:
    """Return the logged-in user from session state, or None."""
    su = st.session_state.get("user")
    if su is None:
        return None
    if not isinstance(su, SessionUser):
        # Stale session (older shape). Force re-login.
        st.session_state.pop("user", None)
        return None
    return su


def logout() -> None:
    """Clear session state and rerun."""
    for key in ("user",):
        st.session_state.pop(key, None)
    st.rerun()


async def authenticate(email: str, password: str) -> SessionUser | None:
    """Verify email + password against the `users` table.

    On success: touch last_login_at, store the SessionUser in
    st.session_state, and return the user. On failure: return None.

    Must be awaited via `db.run_async(...)` from the sync Streamlit page.
    """
    user = await crud_user.get_by_email(email.strip().lower())
    if user is None:
        return None
    if user.role not in (
        DashboardRole.LOCAL_VOLUNTEER,
        DashboardRole.EXPERT,
        DashboardRole.ADMIN,
    ):
        return None
    if not crud_user.verify_password(password, user.password_hash):
        return None
    await crud_user.touch_last_login(user.id)
    _set_session_user(user)
    return SessionUser(
        user_id=str(user.id),
        email=user.email or "",
        role=user.role,
        display_name=user.name,
    )


def render_login_form() -> None:
    """Show email + password fields and dispatch to `authenticate`."""
    st.title("🔐 Pucho Dashboard Login")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", placeholder="volunteer@example.org")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
            return
        user = db_run_async(authenticate(email, password))
        if user is None:
            st.error("Invalid credentials. Check your email and password.")
            return
        st.success(f"Welcome back, {user.display_name or user.email}.")
        st.rerun()


def require_login() -> SessionUser:
    """Block the page if not logged in. Returns the current user."""
    user = get_session_user()
    if user is None:
        st.warning("Please log in to access the dashboard.")
        render_login_form()
        st.stop()
    return user


def require_role(*allowed: Role) -> SessionUser:
    """Block the page if not logged in *or* not in the allowed roles."""
    user = require_login()
    if user.role not in allowed:
        st.error(
            f"This page requires one of the following roles: {', '.join(allowed)}. "
            f"You are signed in as **{user.role}**."
        )
        st.stop()
    return user


def render_sidebar_user_info() -> None:
    """Render the logged-in badge + logout button. Call from app.py only."""
    user = get_session_user()
    if user is None:
        return
    with st.sidebar:
        st.markdown(f"**Signed in as** {user.display_name or user.email}")
        st.caption(f"Role: `{user.role}`")
        if st.button("Log out", use_container_width=True):
            logout()


# Late import to avoid a circular import (auth.py ↔ db.py).
from services.dashboard.db import run_async as db_run_async  # noqa: E402