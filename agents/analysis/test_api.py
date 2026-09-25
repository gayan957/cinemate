"""
Call the running Analysis agent over HTTP.

Start the service first, then:
    python agents/analysis/test_api.py
"""
import sys

import requests

sys.path.insert(0, ".")
from shared.config import ANALYSIS_URL

BATCH = [
    {
        "doc_id": "m1",
        "text": "Stunning visuals and a career-best performance from the lead. "
                "The score by Hans Zimmer lifts every scene. I was moved.",
    },
    {
        "doc_id": "m2",
        "text": "Slow, overlong and poorly written. The dialogue is wooden "
                "and the characters never feel real. A waste of a good cast.",
    },
    {
        "doc_id": "m3",
        "text": "",                       # a film with no reviews
    },
]


def main():
    print(requests.get(f"{ANALYSIS_URL}/health", timeout=10).json())

    response = requests.post(
        f"{ANALYSIS_URL}/analyse-batch", json=BATCH, timeout=120
    )
    response.raise_for_status()

    for item in response.json():
        print(f"\n--- {item['doc_id']} ---")
        print(f"  sentiment : {item['sentiment']} "
              f"({item['sentiment_score']:.3f})")
        print(f"  entities  : {len(item['entities'])}")
        print(f"  reviews   : {item['review_count']}")
        print(f"  summary   : {item['summary'][:120]}")


if __name__ == "__main__":
    main()