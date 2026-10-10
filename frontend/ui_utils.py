"""Data shaping and safe HTML for CineMate's Guardian-powered frontend.

This module is intentionally independent of Streamlit, so it can be tested alone.
"""
from __future__ import annotations

import html
from typing import Any
from urllib.parse import urlparse


def animated_headline_html() -> str:
    """Keep one accessible heading while revealing its visible letters in order."""
    lines = []
    index = 0
    for text, tag in (("Find your next", "span"), ("great watch.", "em")):
        letters = []
        for character in text:
            content = "&nbsp;" if character == " " else html.escape(character)
            letters.append(
                f'<span class="cm-headline-letter" style="--cm-letter-index:{index}">{content}</span>'
            )
            index += 1
        lines.append(f'<{tag} class="cm-headline-line" aria-hidden="true">{"".join(letters)}</{tag}>')
    return (
        '<h1 class="cm-animated-headline" aria-label="Find your next great watch.">'
        + "<br>".join(lines) + "</h1>"
    )


def label_for_media(media_type: str | None) -> str:
    return "TV series" if media_type == "tv" else "Movie"


def useful_recommendations(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Discard malformed recommendations; never invent film data."""
    entries = result.get("recommendations") or []
    if not isinstance(entries, list):
        return []
    return [r for r in entries if isinstance(r, dict) and r.get("title")]


def safe_image_url(value: Any) -> str | None:
    """Only allow HTTPS/HTTP image URLs into the generated HTML."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlparse(value)
        if url.scheme not in {"https", "http"} or not url.netloc:
            return None
    except ValueError:
        return None
    return value


def poster_for(recommendation: dict[str, Any], posters: list[dict[str, Any]]) -> str | None:
    title = str(recommendation.get("title") or "").casefold().strip()
    year = recommendation.get("year")
    for poster in posters or []:
        if not isinstance(poster, dict):
            continue
        if str(poster.get("title") or "").casefold().strip() != title:
            continue
        if year is not None and poster.get("year") not in (None, year, str(year)):
            continue
        return safe_image_url(poster.get("poster_url"))
    return None


def api_error_message(status: int, detail: str = "") -> str:
    if status == 400:
        return detail or "Try rephrasing your request."
    if status == 401:
        return "Your session has expired. Please log in again."
    if status == 429:
        return detail or "Your daily request limit has been reached. Try again tomorrow."
    if status == 503:
        return "The request took too long. Please try again shortly."
    return detail if 400 <= status < 500 else "Something went wrong. Please try again."


def safe_details(response: Any) -> str:
    try:
        detail = response.json().get("detail", "")
        return detail if isinstance(detail, str) else ""
    except (ValueError, AttributeError, TypeError):
        return ""


def media_card_html(recommendation: dict[str, Any], posters: list[dict[str, Any]], rank: int) -> str:
    """Compact results card, safely escaped for Streamlit HTML rendering."""
    e = lambda x: html.escape(str(x), quote=True)
    title = e(recommendation.get("title") or "Unknown title")
    year = e(recommendation.get("year") or "")
    kind = e(label_for_media(recommendation.get("media_type")))
    poster_url = poster_for(recommendation, posters)
    if poster_url:
        img = f'<img src="{e(poster_url)}" alt="Poster for {title}" loading="lazy" />'
    else:
        img = '<div class="cm-poster-empty" aria-label="Poster unavailable">🎬</div>'
    year_text = f'<span class="cm-card-year">{year}</span>' if year else ""
    # Score is a hybrid retrieval value, *not* a star rating or percentage.
    return (
        '<article class="cm-film-card">'
        f'<div class="cm-film-poster">{img}</div>'
        '<div class="cm-film-details">'
        f'<span class="cm-result-index">MATCH {rank:02d}</span>'
        f'<h3>{title}</h3>'
        f'<div class="cm-film-meta"><span>{kind}</span>{year_text}</div>'
        '<div class="cm-film-caption">Selected from the CineMate database for your request.</div>'
        '</div></article>'
    )
