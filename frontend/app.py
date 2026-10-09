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


def hero(has_results: bool) -> None:
    if has_results:
        title = 'Here are your<br><span class="cm-accent">perfect picks.</span>'
        subtitle = "Recommendations based on what you asked for."
        css_class = "cm-hero cm-hero-results"
    else:
        title = 'Find your next<br><span class="cm-accent">movie or show</span> with AI.'
        subtitle = "Describe your mood. We'll find something worth watching."
        css_class = "cm-hero"
    st.markdown(
        f'<section class="{css_class}"><span class="cm-tag">AI MOVIE &amp; TV ASSISTANT</span><h1>{title}</h1><p>{subtitle}</p></section>',
        unsafe_allow_html=True,
    )


def set_example(text: str) -> None:
    st.session_state.query_text = text


def request_recommendations(query: str) -> None:
    with st.spinner("Finding your best matches…"):
        response = post("/ask", {"query": query.strip()}, auth=True)
    if response is None:
        return
    if response.status_code == 200:
        st.session_state.result = response.json()
        st.session_state.pending_query = query.strip()
        st.rerun()
    else:
        if response.status_code == 401:
            st.session_state.token = None
            st.warning("Please sign in again.")
            st.rerun()
        else:
            st.error(api_error_message(response.status_code, safe_details(response)))


def search_area(has_results: bool) -> None:
    with st.container(key="search_panel"):
        with st.form("search_form", border=False):
            input_col, submit_col = st.columns([5, 1], vertical_alignment="bottom")
            with input_col:
                query = st.text_input(
                    "Describe what you feel like watching",
                    placeholder="e.g. A funny TV series with short episodes",
                    label_visibility="collapsed",
                    key="query_text",
                )
            with submit_col:
                submitted = st.form_submit_button("Find matches →", type="primary", use_container_width=True)
        if submitted:
            if query.strip():
                request_recommendations(query)
            else:
                st.warning("Describe what you're in the mood for first.")
        if not has_results:
            with st.container(key="example_buttons"):
                cols = st.columns(4)
                for col, example in zip(cols, EXAMPLES):
                    with col:
                        st.button(example, key=f"example_{EXAMPLES.index(example)}", use_container_width=True,
                                  on_click=set_example, args=(example,))


def clarification(result: dict[str, Any]) -> None:
    st.info(result.get("question") or "Can you tell me a little more?")
    options = result.get("options") or []
    if options:
        for i, option in enumerate(options):
            if st.button(str(option), key=f"clarify_{i}"):
                combined = f"{st.session_state.pending_query}, {option}"
                request_recommendations(combined)


def recommendation_cards(result: dict[str, Any]) -> None:
    recommendations = useful_recommendations(result)
    if not recommendations:
        st.info("No recommendation cards were returned for this request.")
        return
    st.markdown('<div class="cm-section-label">Your top recommendations</div>', unsafe_allow_html=True)
    posters = result.get("posters") or []
    cols = st.columns(min(len(recommendations), 3), gap="medium")
    for number, recommendation in enumerate(recommendations[:3], start=1):
        with cols[number - 1]:
            with st.container(border=True, key=f"recommendation_{number}"):
                poster_url = poster_for(recommendation, posters)
                image_col, text_col = st.columns([1, 1.13], vertical_alignment="top", gap="small")
                with image_col:
                    if poster_url:
                        st.image(poster_url, use_container_width=True)
                    else:
                        st.markdown('<div class="cm-poster-fallback">🎬<br>Poster unavailable</div>', unsafe_allow_html=True)
                with text_col:
                    st.markdown(f"**{number}. {recommendation['title']}**")
                    meta_parts = [str(recommendation.get("year") or "") ,label_for_media(recommendation.get("media_type"))]
                    st.caption(" · ".join(piece for piece in meta_parts if piece))
                    sentiment = recommendation.get("sentiment")
                    if sentiment and sentiment != "unavailable":
                        st.caption(f"Review sentiment: {sentiment}")
                with st.expander("Why this match?"):
                    st.write(recommendation.get("reason") or "Selected from the movie database for your request.")
                    score = recommendation.get("retrieval_score")
                    if isinstance(score, (int, float)):
                        st.caption(f"Retrieval score: {score:.3f} (not a viewer rating)")
                    if recommendation.get("doc_id"):
                        st.caption(f"Database evidence: {recommendation['doc_id']}")


def results_section(result: dict[str, Any]) -> None:
    if result.get("needs_clarification"):
        clarification(result)
        return
    if result.get("relaxed_filters"):
        st.warning("Some search filters were relaxed: " + ", ".join(map(str, result["relaxed_filters"])))
    if result.get("notice"):
        st.info(str(result["notice"]))
    recommendation_cards(result)
    if result.get("answer"):
        with st.expander("Read CineMate's full explanation"):
            st.markdown(result["answer"])
    with st.expander("How your answer was produced"):
        st.write("Agents used: " + ", ".join(map(str, result.get("agents_used") or [])))
        st.caption("Trace ID: " + str(result.get("trace_id") or "Not available"))
        st.caption("Recommendations are linked to retrieved database records. AI-generated explanations can be imperfect.")
        recommendations = useful_recommendations(result)
        if recommendations:
            rows = [{**rec, "media_type": label_for_media(rec.get("media_type"))} for rec in recommendations]
            st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    apply_theme()
    if not st.session_state.token:
        auth_screen()
    else:
        top_bar(authenticated=True)
        has_results = st.session_state.result is not None
        hero(has_results)
        search_area(has_results)
        if st.session_state.result:
            results_section(st.session_state.result)
    st.markdown(
        '<div class="cm-bottom">CineMate uses TMDB data but is not endorsed or certified by TMDB. It recommends titles; it does not stream them.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
