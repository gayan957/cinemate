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
