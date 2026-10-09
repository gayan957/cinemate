"""CineMate Streamlit UI: communicates only with the Guardian service.

Launch from the repository root:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import Any

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from shared.config import GUARDIAN_URL  # noqa: E402
from frontend.ui_utils import (  # noqa: E402
    api_error_message,
    label_for_media,
    poster_for,
    safe_details,
    useful_recommendations,
)

st.set_page_config(page_title="CineMate · AI Movie Guide", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")

EXAMPLES = [
    "funny movies",
    "something like Interstellar",
    "family movies under 2 hours",
    "feel-good TV shows",
]
STATE_DEFAULTS = {
    "token": None,
    "username": None,
    "query_text": "",
    "pending_query": "",
    "result": None,
}
for state_key, default in STATE_DEFAULTS.items():
    st.session_state.setdefault(state_key, default)


def apply_theme() -> None:
    css_path = Path(__file__).parent / "styles.css"
    photo_path = Path(__file__).parent / "assets" / "cinema-backdrop.jpg"
    image_uri = "none"
    if photo_path.is_file():
        encoded = base64.b64encode(photo_path.read_bytes()).decode("ascii")
        image_uri = f'url("data:image/jpeg;base64,{encoded}")'
    css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    st.markdown(f"<style>:root{{--cinemate-hero:{image_uri};}}\n{css}</style>", unsafe_allow_html=True)


def post(path: str, payload: dict[str, Any], *, auth: bool = False) -> requests.Response | None:
    """The ONLY HTTP connection the frontend makes is to Guardian."""
    headers = {}
    if auth:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        return requests.post(f"{GUARDIAN_URL}{path}", json=payload, headers=headers, timeout=120)
    except requests.Timeout:
        st.error("That request took too long. Please try again.")
    except requests.ConnectionError:
        st.error("CineMate is unavailable. Check that the Guardian service is running.")
    except requests.RequestException:
        st.error("We couldn't reach CineMate. Please try again.")
    return None


def brand() -> None:
    st.markdown('<div class="cm-brand"><span class="cm-mark">●</span><span><span class="cm-coral">Cine</span>Mate</span></div>', unsafe_allow_html=True)


def top_bar(authenticated: bool) -> None:
    col_brand, col_action = st.columns([5, 1], vertical_alignment="center")
    with col_brand:
        brand()
    with col_action:
        if authenticated and st.button("Log out", use_container_width=True):
            for state_key in STATE_DEFAULTS:
                st.session_state[state_key] = STATE_DEFAULTS[state_key]
            st.rerun()


def auth_screen() -> None:
    top_bar(authenticated=False)
    left, right = st.columns([1.13, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            """<section class="cm-auth-info">
            <span class="cm-tag">YOUR AI MOVIE &amp; TV ASSISTANT</span>
            <h1>Find your next<br><span class="cm-accent">movie or show</span><br>with AI.</h1>
            <p>Tell CineMate what you're in the mood for. Get three grounded recommendations without endless scrolling.</p>
            <div class="cm-auth-features"><span>Natural-language search</span><span>Movie &amp; TV recommendations</span><span>Reasons for every match</span></div>
            </section>""",
            unsafe_allow_html=True,
        )
    with right:
        with st.container(border=True, key="auth_panel"):
            login_tab, signup_tab = st.tabs(["Log in", "Create account"])
            with login_tab:
                st.subheader("Welcome back")
                st.caption("Continue to your AI movie guide.")
                with st.form("login_form", clear_on_submit=False):
                    username = st.text_input("Username", placeholder="Enter your username")
                    password = st.text_input("Password", type="password", placeholder="Enter your password")
                    submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
                if submitted:
                    if not username.strip() or not password:
                        st.warning("Enter your username and password.")
                    else:
                        response = post("/login", {"username": username.strip(), "password": password})
                        if response is not None:
                            if response.status_code == 200:
                                token = response.json().get("token")
                                if token:
                                    st.session_state.token = token
                                    st.session_state.username = username.strip()
                                    st.rerun()
                                else:
                                    st.error("The login response did not contain a token.")
                            else:
                                st.error("Incorrect username or password.")
            with signup_tab:
                st.subheader("Create your account")
                st.caption("Only a username, password and age are needed.")
                with st.form("register_form", clear_on_submit=False):
                    new_user = st.text_input("Username", key="register_username", placeholder="Choose a username")
                    new_pass = st.text_input("Password", key="register_password", type="password", help="At least 8 characters")
                    confirm_pass = st.text_input("Confirm password", type="password")
                    age = st.number_input("Age", min_value=10, max_value=100, value=20, step=1)
                    register = st.form_submit_button("Create account", type="primary", use_container_width=True)
                if register:
                    if not new_user.strip() or len(new_pass) < 8:
                        st.warning("Enter a username and a password of at least 8 characters.")
                    elif new_pass != confirm_pass:
                        st.warning("Your passwords don't match.")
                    else:
                        response = post("/register", {"username": new_user.strip(), "password": new_pass, "age": int(age)})
                        if response is not None:
                            if response.status_code == 200:
                                st.success("Account created. Switch to Log in to continue.")
                            else:
                                st.error(api_error_message(response.status_code, safe_details(response)))


def main() -> None:
    apply_theme()
    if not st.session_state.token:
        auth_screen()
    else:
        top_bar(authenticated=True)
        st.title("What do you feel like watching?")
        query = st.text_input("Describe your movie or TV request", key="query_text")
        if st.button("Find matches", type="primary") and query.strip():
            with st.spinner("Searching for movie and TV recommendations..."):
                response = post("/ask", {"query": query.strip()}, auth=True)
            if response is not None and response.status_code == 200:
                st.session_state.result = response.json()
                st.session_state.pending_query = query.strip()
            elif response is not None:
                st.error(api_error_message(response.status_code, safe_details(response)))
        if st.session_state.result:
            result = st.session_state.result
            if result.get("needs_clarification"):
                st.info(result.get("question", "Could you clarify your request?"))
            else:
                st.markdown(result.get("answer") or "No response available.")
                for rec in useful_recommendations(result)[:3]:
                    st.write(f"**{rec.get('title')}** — {label_for_media(rec.get('media_type'))}")
    st.caption("CineMate uses TMDB data but is not endorsed or certified by TMDB.")


if __name__ == "__main__":
    main()
