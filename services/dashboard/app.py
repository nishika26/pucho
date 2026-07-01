"""Pucho review dashboard (Streamlit) — role-based navigation entrypoint.

Login gate + a role-aware navigation: local volunteers see only the Local
Volunteer page; experts (and admins) also see the Expert page. Page scripts
live in `views/` (not the special `pages/` folder) so Streamlit doesn't
auto-mount them — navigation is built explicitly here by role.

Run locally:
    PYTHONPATH=. uv run streamlit run services/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from services.dashboard.auth import (
    get_session_user,
    render_sidebar_user_info,
    require_login,
)

st.set_page_config(
    page_title="Pucho Dashboard",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="expanded",
)


def home() -> None:
    """Landing page: what Pucho is + what THIS user does here."""
    user = get_session_user()
    st.title("🤝 Pucho — Review Dashboard")
    st.markdown(
        """
**Pucho** ek WhatsApp helpline hai jo India ke sheher ke gareeb logon ko unke
**kanooni (legal), health, aur paise / sarkari yojana** ke sawaalon mein sahi
aur personalised madad deta hai — **voice ya text** se, unki apni bhaasha mein
aur unke padhne-likhne ke level ke hisaab se.

Bot jo bhi jawab bhejta hai, wo yahan **human review** ke liye aata hai. Yeh
Pucho ka human-in-the-loop knowledge loop hai:

1. **Local volunteers** sawaal mein zameeni (local) jaankari jodte hain.
2. **Domain experts** jawab ko check karte hain, behtar banate hain, phir
   approve karte hain.
3. Approved jaankari wapas bot ke **knowledge base** mein jaati hai — isse Pucho
   asli baaton se aur behtar hota jaata hai.
        """
    )

    role = user.role if user else None
    st.divider()
    if role == "local_volunteer":
        st.subheader("Aap Local Volunteer ke roop mein signed in hain 🙋")
        st.markdown(
            "- Sidebar mein **Local Volunteer** page kholein.\n"
            "- Har pending sawaal aur bot ka jawab padhein.\n"
            "- **Local jaankari** jodein (paas ka daftar, local niyam, zameeni "
            "tip) jo expert kaam mein le sake — phir **Save** karein."
        )
    elif role == "expert":
        st.subheader("Aap Domain Expert ke roop mein signed in hain 🧑‍⚖️")
        st.markdown(
            "- Apne domain ka **Expert** page kholein.\n"
            "- Sawaal, bot ka jawab, aur volunteer ka input dekhein.\n"
            "- Apni **expert jaankari** jodein, phir **Approve** karein — isse "
            "behtar jawab knowledge base mein add hota hai (sirf jab aap kuch "
            "naya jodte hain).\n"
            "- Aap **Local Volunteer** page bhi khol kar local jaankari jod sakte "
            "hain."
        )
    elif role == "admin":
        st.subheader("Aap Admin ke roop mein signed in hain 🛠️")
        st.markdown(
            "- Aapke paas **dono** pages — Local Volunteer aur Expert — ka access "
            "hai, sabhi domains ke liye."
        )
    else:
        st.info("Aapke account ko abhi koi dashboard role nahi mila hai — admin se poochein.")


# --- login gate, then role-based navigation ---------------------------------
user = require_login()
render_sidebar_user_info()

home_page = st.Page(home, title="Home", icon="🏠", default=True)
volunteer_page = st.Page(
    "views/1_🙋_Local_Volunteer.py", title="Local Volunteer", icon="🙋"
)
expert_page = st.Page("views/2_🧑‍⚖️_Expert.py", title="Expert", icon="🧑‍⚖️")

# Experts + admins see both pages; local volunteers see only their own.
if user.role in ("expert", "admin"):
    pages = [home_page, volunteer_page, expert_page]
else:  # local_volunteer
    pages = [home_page, volunteer_page]

st.navigation(pages).run()
