"""
Check the NLP functions work, before wrapping them in a web service.

Usage:
    python agents/analysis/test_nlp.py
"""
import sys
sys.path.insert(0, ".")

from agents.analysis import nlp_tools

POSITIVE = (
    "Christopher Nolan has made something remarkable here. "
    "Matthew McConaughey gives the performance of his career, and the "
    "score by Hans Zimmer is extraordinary. The visuals are stunning "
    "throughout. I left the cinema genuinely moved by what I had seen. "
    "Warner Bros should be proud of backing a film this ambitious."
)

WITH_SPOILER = (
    "The first two acts are gripping and beautifully shot. "
    "But it is revealed that the captain was behind everything all along. "
    "The pacing in the middle section drags slightly. "
    "In the end the hero dies saving the crew, which felt unearned."
)

NEGATIVE = (
    "A tedious and overlong mess. The dialogue is wooden, the pacing "
    "is glacial, and none of the characters behave like real people. "
    "I checked my watch four times. A waste of a talented cast."
)


def show(title, text):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")

    entities = nlp_tools.extract_entities(text)
    print("Entities:")
    for e in entities:
        print(f"  {e['label']:<14} {e['text']}")

    label, score = nlp_tools.analyse_sentiment(text)
    print(f"\nSentiment: {label} (confidence {score:.3f})")

    removed = nlp_tools.count_removed(text)
    print(f"Spoiler sentences removed: {removed}")

    print(f"\nSummary:\n  {nlp_tools.summarise(text)}")


if __name__ == "__main__":
    show("POSITIVE REVIEW", POSITIVE)
    show("REVIEW CONTAINING SPOILERS", WITH_SPOILER)
    show("NEGATIVE REVIEW", NEGATIVE)