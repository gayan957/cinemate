"""Small, dependency-free helpers for the CineMate Streamlit interface."""

from __future__ import annotations

from typing import Any


def label_for_media(media_type: str | None) -> str:
    return "TV series" if media_type == "tv" else "Movie"
