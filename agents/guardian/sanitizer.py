"""
Input cleaning, attack detection, and output checking.
"""
import html
import re
import sys

sys.path.insert(0, ".")
from shared.config import MAX_QUERY_LENGTH


# ==================================================================
# STEP 57 — Cleaning
# ==================================================================
def sanitize(text: str) -> str:
    """
    Neutralise dangerous characters and cap the length.

    Truncating rather than rejecting is deliberate: a user who pastes
    something long should get an answer, not an error.
    """
    if not text:
        return ""

    text = html.escape(text)                     # < becomes &lt;
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)  # control characters
    text = re.sub(r"\s+", " ", text).strip()     # collapse whitespace

    return text[:MAX_QUERY_LENGTH]


# ==================================================================
# STEP 58 — Prompt injection
# ==================================================================
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(the\s+)?(previous|above|prior|earlier)\s+instructions?",
    r"disregard\s+(the\s+)?(system|above|previous|all)",
    r"forget\s+(everything|all|your|the)\s",
    r"you\s+are\s+now\s+(a|an|the)\s",
    r"act\s+as\s+(if\s+you\s+are\s+)?(a|an)\s+\w+\s+(with\s+no|without)",
    r"(reveal|show|print|repeat|output)\s+(me\s+)?(your\s+)?(the\s+)?"
    r"(system\s+)?(prompt|instructions?|rules)",
    r"what\s+(are|were)\s+your\s+(original\s+)?instructions",
    r"\bsystem\s*:\s*",
    r"\[\s*(system|assistant|admin)\s*\]",
    r"<\s*script",
    r"javascript\s*:",
    r"\bDROP\s+TABLE\b",
    r"\bUNION\s+SELECT\b",
]

INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)

SPECIAL_CHAR_LIMIT = 0.4


def detect_injection(text: str):
    """
    Returns (is_safe, reason).

    Checked BEFORE the text reaches the language model. Once an
    instruction is inside the prompt, it is too late.
    """
    if not text:
        return False, "Empty request"

    match = INJECTION_RE.search(text)
    if match:
        return False, "Request contains a prompt injection pattern"

    special = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if len(text) > 10 and special / len(text) > SPECIAL_CHAR_LIMIT:
        return False, "Request contains too many special characters"

    if len(text.strip()) < 3:
        return False, "Request is too short to search for"

    return True, "ok"


# ==================================================================
# STEP 59 — Outbound checking
# ==================================================================
ADULT_MARKERS = [
    "nc-17", "explicit sexual", "graphic sexual",
    "graphic gore", "extreme violence", "rated x",
]

LEAK_MARKERS = [
    "my instructions are", "system prompt", "you are the planning module",
    "i was told to", "my system message",
]


def check_output(text: str, user_age: int):
    """
    Checked BEFORE the answer reaches the user.

    Two jobs: age suitability, and making sure the model has not been
    talked into revealing its own instructions.
    """
    if not text:
        return True, "ok"

    lowered = text.lower()

    if user_age < 18:
        for marker in ADULT_MARKERS:
            if marker in lowered:
                return False, "Content not suitable for this account"

    for marker in LEAK_MARKERS:
        if marker in lowered:
            return False, "Response may reveal internal instructions"

    return True, "ok"


def max_age_rating_for(age: int) -> str:
    """Which certifications this user may see. Used as a search filter."""
    if age < 13:
        return "PG"
    if age < 17:
        return "PG-13"
    return "R"