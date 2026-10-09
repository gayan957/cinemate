"""Small, dependency-free helpers for the CineMate Streamlit interface."""

from __future__ import annotations

from typing import Any


def label_for_media(media_type: str | None) -> str:
    return "TV series" if media_type == "tv" else "Movie"

def useful_recommendations(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only well-formed entries that can be presented safely."""
    entries = result.get("recommendations") or []
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict) and item.get("title")]

def poster_for(recommendation: dict[str, Any], posters: list[dict[str, Any]]) -> str | None:
    """Match a recommendation to its poster without relying on list order."""
    title = str(recommendation.get("title") or "").casefold().strip()
    year = recommendation.get("year")
    for poster in posters or []:
        if str(poster.get("title") or "").casefold().strip() != title:
            continue
        if year is not None and poster.get("year") not in (None, year):
            continue
        return poster.get("poster_url") or None
    return None

def api_error_message(status: int, detail: str = "") -> str:
    """Translate backend status codes into concise, non-sensitive UI feedback."""
    if status == 400:
        return detail or "The request could not be processed. Try different wording."
    if status == 401:
        return "Your session has expired. Please log in again."
    if status == 429:
        return detail or "You've reached your daily question limit. Please try tomorrow."
    if status == 503:
        return "CineMate is taking longer than expected. Please try again shortly."
    return detail if 400 <= status < 500 else "Something went wrong. Please try again."
