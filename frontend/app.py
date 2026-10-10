"""CineMate — cinematic Streamlit UI.

All requests go to Guardian only (login, register, ask).
From the repository root: streamlit run frontend/app.py
"""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path
from typing import Any

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.config import GUARDIAN_URL  # noqa: E402
from frontend.ui_utils import (  # noqa: E402
    api_error_message, label_for_media, media_card_html, animated_headline_html,
    safe_details, useful_recommendations,
)

st.set_page_config(
    page_title="CineMate | Your AI Movie Guide",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

EXAMPLES = (
    "funny movies",
    "something like Interstellar",
    "family movies under 2 hours",
    "feel-good TV shows",
)

STATE = {
    "token": None,
    "username": "",
    "query_text": "",
    "pending_query": "",
    "result": None,
}
for key, default in STATE.items():
    st.session_state.setdefault(key, default)


@st.cache_data(show_spinner=False)
def stylesheet() -> str:
    css = (Path(__file__).parent / "styles.css").read_text(encoding="utf-8")
    bg = Path(__file__).parent / "assets" / "cinema-backdrop.jpg"
    if bg.exists():
        encoded = base64.b64encode(bg.read_bytes()).decode("ascii")
        css = css.replace("__CINEMA_IMAGE__", f'data:image/jpeg;base64,{encoded}')
    else:
        css = css.replace("__CINEMA_IMAGE__", "")
    return css


def apply_theme() -> None:
    st.markdown(f"<style>{stylesheet()}</style>", unsafe_allow_html=True)


def post(path: str, payload: dict[str, Any], *, auth: bool = False) -> requests.Response | None:
    """The only network calls made by the Streamlit frontend go to Guardian."""
    headers = {"Authorization": f"Bearer {st.session_state.token}"} if auth else {}
    try:
        return requests.post(
            f"{GUARDIAN_URL}{path}", json=payload, headers=headers, timeout=120
        )
    except requests.Timeout:
        st.error("That request took too long. Please try again.")
    except requests.ConnectionError:
        st.error("Cannot connect to CineMate. Make sure Guardian is running.")
    except requests.RequestException:
        st.error("CineMate is unavailable. Please try again.")
    return None


LOGO = '''<div class="cm-brand" aria-label="CineMate">
<svg viewBox="0 0 44 44" width="42" height="42" aria-hidden="true">
<circle cx="22" cy="22" r="20" fill="#fa6269"/>
<circle cx="22" cy="22" r="4" fill="#091017"/>
<circle cx="21.6" cy="9.7" r="4.7" fill="#091017"/>
<circle cx="33.5" cy="19.1" r="4.7" fill="#091017"/>
<circle cx="28.4" cy="32.3" r="4.7" fill="#091017"/>
<circle cx="14.5" cy="32" r="4.7" fill="#091017"/>
<circle cx="10.4" cy="17.7" r="4.7" fill="#091017"/>
</svg><span><span>Cine</span>Mate</span></div>'''


def header(logged_in: bool) -> None:
    with st.container(key="cm_header"):
        left, middle, right = st.columns([3.5, 1.8, 1], vertical_alignment="center")
        with left:
            st.markdown(LOGO, unsafe_allow_html=True)
        with middle:
            if logged_in:
                name = html.escape(st.session_state.username or "Viewer")
                st.markdown(f'<div class="cm-header-caption">YOUR MOVIE ASSISTANT &nbsp; · &nbsp; {name}</div>', unsafe_allow_html=True)
        with right:
            if logged_in and st.button("Log out", key="cm_logout", use_container_width=True):
                for key, default in STATE.items():
                    st.session_state[key] = default
                st.rerun()


def auth_screen() -> None:
    st.markdown('<div class="cm-page-auth"></div>', unsafe_allow_html=True)
    header(False)
    with st.container(key="cm_auth_layout"):
        left, right = st.columns([1.1, .88], gap="large", vertical_alignment="center")
        with left:
            st.markdown('''<section class="cm-intro cm-intro-auth">
              <span class="cm-eyebrow">CINEMATE &nbsp;/&nbsp; AI MOVIE ASSISTANT</span>
              ''' + animated_headline_html() + '''
              <p>Tell us what you're in the mood for.<br>We'll find the movies and shows that fit.</p>
              <div class="cm-intro-rule"></div>
              <span class="cm-intro-footnote">ONE QUESTION. THREE THOUGHTFUL MATCHES.</span>
              </section>''', unsafe_allow_html=True)
        with right:
            with st.container(key="cm_auth_card"):
                login_tab, signup_tab = st.tabs(["Log in", "Create account"])
                with login_tab:
                    st.markdown('<div class="cm-form-heading">Welcome back<span>Sign in to find your next watch.</span></div>', unsafe_allow_html=True)
                    with st.form("login_form", border=False):
                        username = st.text_input("Username", placeholder="Your username", key="cm_login_username")
                        password = st.text_input("Password", type="password", placeholder="Your password", key="cm_login_password")
                        login_clicked = st.form_submit_button("Log in  →", type="primary", use_container_width=True)
                    if login_clicked:
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
                                        st.error("The login response did not include a token.")
                                else:
                                    st.error("Incorrect username or password.")
                with signup_tab:
                    st.markdown('<div class="cm-form-heading">Join CineMate<span>Create an account in a moment.</span></div>', unsafe_allow_html=True)
                    with st.form("registration_form", border=False):
                        new_user = st.text_input("Username", placeholder="Choose a username", key="cm_signup_username")
                        new_pass = st.text_input("Password", type="password", placeholder="At least 8 characters", key="cm_signup_password")
                        confirm = st.text_input("Confirm password", type="password", placeholder="Repeat password", key="cm_signup_confirmation")
                        age = st.number_input("Age", min_value=10, max_value=100, value=20, step=1, key="cm_signup_age")
                        register_clicked = st.form_submit_button("Create account  →", type="primary", use_container_width=True)
                    if register_clicked:
                        if not new_user.strip() or len(new_pass) < 8:
                            st.warning("Enter a username and a password of at least 8 characters.")
                        elif new_pass != confirm:
                            st.warning("Passwords don't match.")
                        else:
                            response = post("/register", {"username": new_user.strip(), "password": new_pass, "age": int(age)})
                            if response is not None:
                                if response.status_code == 200:
                                    st.success("Account created. Switch to Log in to continue.")
                                else:
                                    st.error(api_error_message(response.status_code, safe_details(response)))
    legal_note()


def legal_note() -> None:
    st.markdown('<div class="cm-footer">CineMate uses TMDB data but is not endorsed or certified by TMDB. CineMate recommends films and shows; it does not stream them.</div>', unsafe_allow_html=True)


def search_example(query: str) -> None:
    st.session_state.query_text = query


def ask(query: str) -> None:
    with st.spinner("Finding the right match for you…"):
        response = post("/ask", {"query": query.strip()}, auth=True)
    if response is None:
        return
    if response.status_code == 200:
        st.session_state.result = response.json()
        st.session_state.pending_query = query.strip()
        st.rerun()
    if response.status_code == 401:
        st.session_state.token = None
        st.session_state.result = None
        st.warning("Your session expired. Please log in again.")
        st.rerun()
    st.error(api_error_message(response.status_code, safe_details(response)))


def search_area(*, with_examples: bool) -> None:
    with st.container(key="cm_search_region"):
        with st.form("cm_search_form", border=False):
            input_col, button_col = st.columns([6, 1.15], gap="small", vertical_alignment="center")
            with input_col:
                text = st.text_input(
                    "What do you feel like watching?",
                    key="query_text",
                    label_visibility="collapsed",
                    placeholder="Describe a movie or TV show you're in the mood for…",
                )
            with button_col:
                submitted = st.form_submit_button("Find matches →", type="primary", use_container_width=True)
        if submitted:
            if text.strip():
                ask(text)
            else:
                st.warning("Describe what you're looking for to get started.")
    if with_examples:
        with st.container(key="cm_example_region"):
            st.markdown('<span class="cm-example-label">TRY SOMETHING LIKE</span>', unsafe_allow_html=True)
            columns = st.columns(4, gap="small")
            for index, (column, phrase) in enumerate(zip(columns, EXAMPLES)):
                with column:
                    st.button(phrase, key=f"cm_example_{index}", use_container_width=True,
                              on_click=search_example, args=(phrase,))


def landing() -> None:
    st.markdown('''<section class="cm-intro cm-landing-intro">
      <span class="cm-eyebrow">YOUR AI MOVIE &amp; TV ASSISTANT</span>
      <h1>Find your next<br><em>movie or show.</em></h1>
      <p>Tell CineMate what you're in the mood for.</p>
      </section>''', unsafe_allow_html=True)
    search_area(with_examples=True)
    st.markdown('<div class="cm-landing-bottom"><span class="cm-small-dot"></span> MADE FOR THE MOMENT YOU CAN\'T DECIDE WHAT TO WATCH</div>', unsafe_allow_html=True)


def clarification(result: dict[str, Any]) -> None:
    question = html.escape(str(result.get("question") or "Can you tell me more?"))
    st.markdown(f'<div class="cm-clarify-title">Just one more thing…<p>{question}</p></div>', unsafe_allow_html=True)
    options = result.get("options") or []
    if options:
        columns = st.columns(min(len(options), 4))
        for index, option in enumerate(options):
            with columns[index % len(columns)]:
                if st.button(str(option), key=f"cm_clarify_{index}", use_container_width=True):
                    ask(f"{st.session_state.pending_query}, {option}")


def results(result: dict[str, Any]) -> None:
    st.markdown('''<section class="cm-intro cm-results-intro">
      <span class="cm-eyebrow">PERSONALIZED DISCOVERY</span>
      <h1>Here are your<br><em>best matches.</em></h1>
      <p>Picked for the way you want to watch.</p>
      </section>''', unsafe_allow_html=True)
    search_area(with_examples=False)
    if result.get("needs_clarification"):
        clarification(result)
        return
    if result.get("relaxed_filters"):
        st.info("We widened your search by relaxing: " + ", ".join(map(str, result["relaxed_filters"])))
    if result.get("notice"):
        st.info(str(result["notice"]))

    matches = useful_recommendations(result)[:3]
    if not matches:
        if result.get("answer"):
            st.write(result["answer"])
        else:
            st.info("No recommendations were returned. Try a different description.")
        return

    st.markdown(
        f'<div class="cm-section-header"><div><span class="cm-eyebrow">FROM YOUR REQUEST</span><h2>{len(matches)} picks for you</h2></div><span class="cm-matches-meta">REAL TITLES · DATABASE-GROUNDED</span></div>',
        unsafe_allow_html=True,
    )
    posters = result.get("posters") or []
    answer = result.get("answer")
    cards = st.columns(len(matches), gap="medium")
    for index, (column, recommendation) in enumerate(
        zip(cards, matches), start=1
    ):
        with column:
            st.markdown(
                media_card_html(recommendation, posters, index),
                unsafe_allow_html=True,
            )

    if answer:
        with st.container(key="cm_recommendation_explanation"):
            st.markdown(
                '<span class="cm-eyebrow">WHY THESE PICKS</span>'
                '<h3 class="cm-explanation-title">Your recommendations</h3>',
                unsafe_allow_html=True,
            )
            st.markdown(answer)

    with st.container(key="cm_result_details"):
        with st.expander("Sources and agent details"):
            for recommendation in matches:
                title = recommendation.get("title") or "Unknown title"
                score = recommendation.get("retrieval_score")
                details = f"**{title}** · {label_for_media(recommendation.get('media_type'))}"
                if recommendation.get("doc_id"):
                    details += f" · Evidence ID: `{recommendation['doc_id']}`"
                if isinstance(score, (int, float)):
                    details += f" · Retrieval score: {score:.3f}"
                st.markdown(details)
            st.caption("Retrieval scores are not audience ratings. AI-generated summaries can be imperfect.")
            st.caption("Agents used: " + ", ".join(map(str, result.get("agents_used") or [])))
            st.caption("Trace ID: " + str(result.get("trace_id") or "Unavailable"))


def main() -> None:
    apply_theme()
    if not st.session_state.token:
        auth_screen()
    else:
        st.markdown('<div class="cm-page-app"></div>', unsafe_allow_html=True)
        header(True)
        if st.session_state.result is None:
            landing()
        else:
            results(st.session_state.result)
        legal_note()


if __name__ == "__main__":
    main()
