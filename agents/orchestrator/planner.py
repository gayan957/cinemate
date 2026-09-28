"""
Turns a messy human sentence into a structured plan.

If the LLM fails, a rule-based fallback keeps the system working.
"""
import json
import os
import re
import sys

from groq import Groq

sys.path.insert(0, ".")
from shared.config import GROQ_API_KEY, LLM_MODEL, LLM_TIMEOUT

client = Groq(api_key=GROQ_API_KEY)

PROMPT_PATH = os.path.join(
    os.path.dirname(__file__), "prompts", "planner.txt"
)
with open(PROMPT_PATH, encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

VAGUE = {
    "something good", "a good movie", "a nice film", "anything",
    "a movie", "something to watch", "recommend something",
    "a film", "something nice", "good movie",
}


# ==================================================================
# STEP 64 — Ask the LLM for a plan
# ==================================================================
def make_plan(query: str) -> dict:
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1,          # near-deterministic for structured output
            # gpt-oss reasons before it answers. Left at the default effort,
            # the reasoning can use the whole budget and leave no JSON.
            # Remove reasoning_effort if LLM_MODEL is not a reasoning model.
            max_tokens=1024,
            reasoning_effort="low",
            response_format={"type": "json_object"},   # guarantees valid JSON
            timeout=LLM_TIMEOUT,
        )
        raw = response.choices[0].message.content.strip()
        return _normalise(_parse_json(raw), query)

    except Exception as e:
        print(f"planner fell back to rules: {e}")
        return fallback_plan(query)


def _parse_json(raw: str) -> dict:
    """Models sometimes wrap JSON in fences or add a sentence."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE)

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # Last resort: find the outermost braces
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))

    raise ValueError("no JSON found in the model's reply")


def _normalise(plan: dict, query: str) -> dict:
    """Fill in anything the model left out, so callers can trust the shape."""
    filters = plan.get("filters") or {}

    # Anything other than movie or tv means "search both"
    media_type = filters.get("media_type")
    if media_type not in ("movie", "tv"):
        media_type = None

    return {
        "search_query": plan.get("search_query") or query,
        "filters": {
            "media_type": media_type,
            "genres": filters.get("genres") or [],
            "max_runtime": filters.get("max_runtime"),
            "min_year": filters.get("min_year"),
        },
        "variants": plan.get("variants") or [],
        "needs_analysis": plan.get("needs_analysis", True),
        "needs_clarification": plan.get("needs_clarification", False),
        "question": plan.get("question"),
        "options": plan.get("options") or [],
        "user_intent": plan.get("user_intent") or query,
    }


# ==================================================================
# STEP 65 — Fallback when the LLM is unavailable
# ==================================================================
RUNTIME_RE = re.compile(
    r"under\s+(?:(\d+)\s*hours?|(\d+)\s*min)", re.IGNORECASE
)
YEAR_RE = re.compile(r"(?:after|since|from)\s+(\d{4})", re.IGNORECASE)
# "show" alone is a series, but "show me a film" is not
TV_RE = re.compile(
    r"\b(?:tv|television|series|sitcoms?|mini-?series|seasons?|episodes?"
    r"|binge)\b|\bshows?\b(?!\s+me\b)",
    re.IGNORECASE,
)
MOVIE_RE = re.compile(r"\b(?:movies?|films?)\b", re.IGNORECASE)


def fallback_plan(query: str) -> dict:
    """
    Rule-based planning. Worse than the LLM, but the system keeps working
    when the free tier is rate limited or the network is down.
    """
    filters = {"media_type": None, "genres": [], "max_runtime": None,
               "min_year": None}

    # Only commit to a type when the request names exactly one
    wants_tv, wants_movie = TV_RE.search(query), MOVIE_RE.search(query)
    if wants_tv and not wants_movie:
        filters["media_type"] = "tv"
    elif wants_movie and not wants_tv:
        filters["media_type"] = "movie"

    match = RUNTIME_RE.search(query)
    if match:
        hours, minutes = match.groups()
        filters["max_runtime"] = int(hours) * 60 if hours else int(minutes)

    match = YEAR_RE.search(query)
    if match:
        filters["min_year"] = int(match.group(1))

    return {
        "search_query": query,
        "filters": filters,
        "variants": [],
        "needs_analysis": True,
        "needs_clarification": query.lower().strip() in VAGUE,
        "question": "What kind of mood are you in?",
        "options": ["Light and funny", "Tense and gripping",
                    "Slow and thoughtful"],
        "user_intent": query,
    }