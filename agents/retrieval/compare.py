"""
Run the same queries through every method and look at the differences.

Usage:
    python agents/retrieval/compare.py
"""
import sys
sys.path.insert(0, ".")

from agents.retrieval.search import Retriever

QUERIES = [
    "Christopher Nolan",                       # exact name - BM25 should win
    "lonely astronaut hopeful ending",         # mood - dense should win
    "heist movie with a clever twist",         # mixed
    "animated film for young children",        # genre-like
    "war drama based on true events",          # mixed
]

METHODS = ["bm25", "fulltext", "dense", "hybrid", "reranked"]


def main():
    retriever = Retriever()

    for query in QUERIES:
        print(f"\n{'=' * 62}\nQUERY: {query}\n{'=' * 62}")

        for method in METHODS:
            results = retriever.search(query, method=method, k=3)
            titles = ", ".join(
                f"{r['title']} ({r['year']})" for r in results
            ) or "no results"
            print(f"  {method:<10} {titles}")

    retriever.close()


if __name__ == "__main__":
    main()