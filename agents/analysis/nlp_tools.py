"""
The NLP work behind the Analysis agent.

Models load once when this module is imported, not per request.
Loading them per request would add several seconds to every query.
"""
import re
import sys

import spacy
from transformers import pipeline

sys.path.insert(0, ".")
from shared.config import SPACY_MODEL, SENTIMENT_MODEL, SUMMARY_MODEL

print("Loading spaCy...")
nlp = spacy.load(SPACY_MODEL)

print("Loading sentiment model...")
sentiment_model = pipeline("sentiment-analysis", model=SENTIMENT_MODEL)

print("Loading summarisation model...")
summariser = pipeline("summarization", model=SUMMARY_MODEL)

print("Analysis models ready")


# ==================================================================
# STEP 48 — Named Entity Recognition
# ==================================================================
KEEP_LABELS = {"PERSON", "ORG", "GPE", "WORK_OF_ART", "DATE"}


def extract_entities(text, limit=15):
    """
    Find people, organisations, places and works mentioned in reviews.

    Duplicates are removed, because a review naming the same actor
    five times should produce one entity, not five.
    """
    doc = nlp(text[:5000])          # cap length, spaCy slows on huge input

    seen, entities = set(), []
    for ent in doc.ents:
        if ent.label_ not in KEEP_LABELS:
            continue

        key = (ent.text.lower(), ent.label_)
        if key in seen:
            continue

        seen.add(key)
        entities.append({"text": ent.text, "label": ent.label_})

        if len(entities) >= limit:
            break

    return entities


# ==================================================================
# STEP 49 — Sentiment
# ==================================================================
NEUTRAL_THRESHOLD = 0.65


def analyse_sentiment(text):
    """
    Returns (label, score).

    Confidence below the threshold becomes neutral. Film reviews are
    often genuinely mixed, and forcing them into positive or negative
    would be dishonest output.
    """
    if not text or len(text.strip()) < 20:
        return "unavailable", 0.0

    try:
        result = sentiment_model(text[:512])[0]
    except Exception as e:
        print(f"sentiment failed: {e}")
        return "unavailable", 0.0

    label = result["label"].lower()
    score = float(result["score"])

    if score < NEUTRAL_THRESHOLD:
        return "neutral", score

    return ("positive" if label == "positive" else "negative"), score


# ==================================================================
# STEP 50 — Spoiler removal
# ==================================================================
SPOILER_PATTERNS = [
    r"\bdies\b", r"\bdied\b", r"\bdeath of\b", r"\bkilled\b", r"\bkills\b",
    r"\bthe ending\b", r"\bfinal scene\b", r"\blast scene\b",
    r"\bturns out\b", r"\bit is revealed\b", r"\brevealed that\b",
    r"\bplot twist\b", r"\btwist\b", r"\bspoiler\b",
    r"\bin the end\b", r"\bfinally\b.{0,30}\bdefeat",
    r"\bsurvives\b", r"\bdoesn't survive\b",
]

SPOILER_RE = re.compile("|".join(SPOILER_PATTERNS), re.IGNORECASE)


def remove_spoilers(text):
    """
    Delete any sentence that looks like it gives away the plot.

    This runs BEFORE summarisation. Filtering afterwards would be too
    late, because the summariser writes new sentences and could rewrite
    a spoiler into different words.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    safe = [s for s in sentences if not SPOILER_RE.search(s)]
    return " ".join(safe).strip()


def count_removed(text):
    """How many sentences were dropped. Useful for the report."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return sum(1 for s in sentences if SPOILER_RE.search(s))


# ==================================================================
# STEP 51 — Summarisation
# ==================================================================
MIN_WORDS_TO_SUMMARISE = 60


def summarise(text, max_length=90, min_length=25):
    """
    Write a short spoiler-free summary.

    Short text passes through unchanged. Forcing a 40-word review
    through a summariser produces worse output than leaving it alone.
    """
    clean = remove_spoilers(text)

    if not clean:
        return ""

    if len(clean.split()) < MIN_WORDS_TO_SUMMARISE:
        return clean

    try:
        result = summariser(
            clean[:1024],           # the model's input limit
            max_length=max_length,
            min_length=min_length,
            do_sample=False,        # deterministic, same input same output
        )
        return result[0]["summary_text"].strip()
    except Exception as e:
        print(f"summarisation failed: {e}")
        return clean[:300]          # fall back to truncated clean text


# ==================================================================
# Everything together for one film
# ==================================================================
def analyse_text(text, doc_id=""):
    """Run all three steps and return one complete result."""
    if not text or len(text.strip()) < 20:
        return {
            "doc_id": doc_id,
            "entities": [],
            "sentiment": "unavailable",
            "sentiment_score": 0.0,
            "summary": "",
            "review_count": 0,
            "spoilers_removed": 0,
        }

    return {
        "doc_id": doc_id,
        "entities": extract_entities(text),
        "sentiment": analyse_sentiment(text)[0],
        "sentiment_score": round(analyse_sentiment(text)[1], 4),
        "summary": summarise(text),
        "review_count": 1,
        "spoilers_removed": count_removed(text),
    }