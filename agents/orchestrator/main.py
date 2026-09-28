"""
Orchestrator agent. The brain. HTTP service on port 8000.

Start with:
    uvicorn agents.orchestrator.main:app --port 8000
"""
import os
import sys

import requests
from fastapi import FastAPI
from groq import Groq

sys.path.insert(0, ".")
from shared.config import (
    GROQ_API_KEY, LLM_MODEL, LLM_TIMEOUT,
    ANALYSIS_URL, ANALYSIS_TIMEOUT,
)
from shared.schemas import UserQuery
from agents.orchestrator.planner import make_plan
from agents.orchestrator.mcp_client import search as mcp_search

app = FastAPI(title="CineMate Orchestrator Agent", version="1.0")
client = Groq(api_key=GROQ_API_KEY)

ANSWER_PROMPT = open(
    os.path.join(os.path.dirname(__file__), "prompts", "answer.txt"),
    encoding="utf-8",
).read()

AGE_LIMITS = {13: "PG", 17: "PG-13"}


@app.get("/health")
def health():
    return {"status": "ok", "agent": "orchestrator"}


@app.post("/process")
async def process(request: UserQuery):
    agents_used = ["orchestrator"]

    # ---- 1. Plan ----
    plan = make_plan(request.query)

    # ---- STEP 66: ask instead of guessing ----
    if plan["needs_clarification"]:
        return {
            "answer": "",
            "recommendations": [],
            "needs_clarification": True,
            "question": plan["question"],
            "options": plan["options"],
            "agents_used": agents_used,
            "relaxed_filters": [],
            "trace_id": "",
        }

    # ---- 2. Age filtering happens during search, not after ----
    filters = dict(plan["filters"])
    for limit, rating in sorted(AGE_LIMITS.items()):
        if request.age < limit:
            filters["max_age_rating"] = rating
            break

    # ---- 3. Retrieve over MCP ----
    try:
        films, relaxed = await mcp_search(
            plan["search_query"], filters, plan["variants"]
        )
        agents_used.append("retrieval")
    except Exception as e:
        print(f"retrieval failed: {e}")
        return _error_response(
            "I could not reach the film database. Please try again.",
            agents_used,
        )


    if not isinstance(films, list):
        print(f"retrieval returned {type(films)}, expected list")
        films = []

    if not films:
        return _error_response(
            "I could not find anything matching that. "
            "Try describing it a different way.",
            agents_used,
        )

    # ---- 4. Analyse over HTTP ----
    analyses, notice = {}, None

    if plan["needs_analysis"]:
        analyses, notice = _analyse(films[:5])
        if analyses:
            agents_used.append("analysis")

    # ---- 5. Write the answer ----
    answer = _write_answer(request.query, films[:5], analyses)

    recommendations = [
        {
            "doc_id": f["doc_id"],
            "title": f["title"],
            "year": f["year"],
            "media_type": f.get("media_type", "movie"),
            "reason": f"Matched with a relevance score of {f['score']:.3f}",
            "sentiment": analyses.get(f["doc_id"], {}).get(
                "sentiment", "unavailable"
            ),
            "retrieval_score": f["score"],
        }
        for f in films[:3]
    ]

    return {
        "answer": answer,
        "recommendations": recommendations,
        "needs_clarification": False,
        "question": None,
        "options": [],
        "agents_used": agents_used,
        "relaxed_filters": relaxed,
        "trace_id": "",
        "notice": notice,
    }


# ==================================================================
# STEP 70 — Survive a missing Analysis agent
# ==================================================================
def _analyse(films):
    """Returns (analyses, notice). A failure here must not stop the answer."""
    batch = [
        {"doc_id": f["doc_id"], "text": f.get("matched_text", "")}
        for f in films
    ]

    try:
        response = requests.post(
            f"{ANALYSIS_URL}/analyse-batch",
            json=batch,
            timeout=ANALYSIS_TIMEOUT,
        )
        response.raise_for_status()
        return {a["doc_id"]: a for a in response.json()}, None

    except requests.RequestException as e:
        print(f"analysis unavailable: {e}")
        return {}, "Review analysis is unavailable, so no summaries are shown."


# ==================================================================
# STEP 71 — Generate the answer
# ==================================================================
def _write_answer(query, films, analyses):
    lines = []
    for f in films:
        analysis = analyses.get(f["doc_id"], {})

        sentiment = analysis.get("sentiment", "unavailable")
        summary = analysis.get("summary", "")

        review_note = (
            f"Reviewers were {sentiment}. {summary}"
            if sentiment != "unavailable"
            else "No reviews available for this title."
        )

        if f.get("media_type") == "tv":
            seasons = f.get("seasons")
            kind = (f"TV series, {seasons} season{'s' if seasons != 1 else ''}"
                    if seasons else "TV series")
            if f.get("runtime"):
                kind += f", about {f['runtime']} minute episodes"
            if f.get("creator"):
                kind += f", created by {f['creator']}"
            if f.get("status"):
                kind += f", {f['status'].lower()}"
        else:
            kind = f"film, {f.get('runtime') or '?'} minutes"

        lines.append(
            f"- {f['title']} ({f['year']}), {kind}, "
            f"{', '.join(f.get('genres') or [])}, rated {f.get('age_rating')}. "
            f"Plot: {(f.get('overview') or '')[:200]}. {review_note}"
        )

    prompt = (
        f"{ANSWER_PROMPT}\n\n"
        f"User's request: {query}\n\n"
        f"Retrieved films:\n" + "\n".join(lines)
    )

    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            # gpt-oss can spend the whole budget reasoning and return
            # nothing, with no error. Keep reasoning short.
            max_tokens=1024,
            reasoning_effort="low",
            timeout=LLM_TIMEOUT,
        )
        answer = (completion.choices[0].message.content or "").strip()
        if not answer:
            raise ValueError("model returned an empty answer")
        return answer

    except Exception as e:
        print(f"answer generation failed: {e}")
        # Still give the user something useful
        return "Here is what I found:\n\n" + "\n".join(
            f"- {f['title']} ({f['year']})" for f in films[:3]
        )


def _error_response(message, agents_used):
    return {
        "answer": message,
        "recommendations": [],
        "needs_clarification": False,
        "question": None,
        "options": [],
        "agents_used": agents_used,
        "relaxed_filters": [],
        "trace_id": "",
    }