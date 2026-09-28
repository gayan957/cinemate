"""
CineMate user interface.

Talks only to the Guardian. It never contacts the other agents directly.

Run with:
    streamlit run frontend/app.py
"""
import sys

import requests
import streamlit as st

sys.path.insert(0, ".")
from shared.config import GUARDIAN_URL

st.set_page_config(page_title="CineMate", page_icon="🎬", layout="centered")

for key in ["token", "pending_query", "result"]:
    st.session_state.setdefault(key, None)


def post(path, payload, auth=False):
    headers = (
        {"Authorization": f"Bearer {st.session_state.token}"} if auth else {}
    )
    return requests.post(
        f"{GUARDIAN_URL}{path}", json=payload, headers=headers, timeout=120
    )


# ==================================================================
# Login
# ==================================================================
if not st.session_state.token:
    st.title("CineMate")
    st.caption("Describe what you feel like watching, in your own words.")

    tab_login, tab_register = st.tabs(["Log in", "Create account"])

    with tab_login:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Log in", type="primary"):
            r = post("/login", {"username": username, "password": password})
            if r.status_code == 200:
                st.session_state.token = r.json()["token"]
                st.rerun()
            else:
                st.error("Incorrect username or password")

    with tab_register:
        new_user = st.text_input("Username", key="reg_user")
        new_pass = st.text_input(
            "Password", type="password", key="reg_pass",
            help="At least 8 characters",
        )
        age = st.number_input("Age", min_value=10, max_value=100, value=20)

        if st.button("Create account"):
            r = post(
                "/register",
                {"username": new_user, "password": new_pass, "age": int(age)},
            )
            if r.status_code == 200:
                st.success("Account created. Now log in.")
            else:
                st.error(r.json().get("detail", "Could not create account"))

    st.stop()


# ==================================================================
# Main app
# ==================================================================
col1, col2 = st.columns([4, 1])
col1.title("CineMate")
if col2.button("Log out"):
    st.session_state.clear()
    st.rerun()

query = st.text_area(
    "What do you feel like watching?",
    placeholder="Something like Interstellar but less sad, under two hours. "
                "Or a funny TV series with short episodes",
    height=90,
)

if st.button("Find something", type="primary") and query.strip():
    with st.spinner("The agents are working..."):
        r = post("/ask", {"query": query}, auth=True)

    if r.status_code == 200:
        st.session_state.result = r.json()
        st.session_state.pending_query = query
    elif r.status_code == 429:
        st.warning(r.json().get("detail"))
    elif r.status_code == 400:
        st.error(r.json().get("detail"))
    else:
        st.error("Something went wrong. Please try again.")

result = st.session_state.result

if result:
    # ---- The system asked a question ----
    if result.get("needs_clarification"):
        st.info(result["question"])

        cols = st.columns(len(result["options"]))
        for col, option in zip(cols, result["options"]):
            if col.button(option):
                combined = f"{st.session_state.pending_query}, {option}"
                with st.spinner("Searching..."):
                    r = post("/ask", {"query": combined}, auth=True)
                if r.status_code == 200:
                    st.session_state.result = r.json()
                    st.rerun()

    # ---- A normal answer ----
    else:
        if result.get("relaxed_filters"):
            st.warning(
                "No exact match, so I relaxed: "
                + ", ".join(result["relaxed_filters"])
            )

        if result.get("notice"):
            st.info(result["notice"])

        st.markdown(result["answer"])

        with st.expander("How this answer was produced"):
            st.write("**Agents used:** " + ", ".join(result["agents_used"]))
            st.write("**Trace ID:** " + str(result.get("trace_id")))
            st.caption(
                "Summaries are AI-generated from user reviews. "
                "Every recommendation comes from a retrieved database record."
            )
            rows = [
                {**r, "media_type": "TV series" if r.get("media_type") == "tv"
                 else "Film"}
                for r in result["recommendations"]
            ]
            st.dataframe(rows, width="stretch")

st.divider()
st.caption(
    "This product uses the TMDB API but is not endorsed or certified by TMDB."
)