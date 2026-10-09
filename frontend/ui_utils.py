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
