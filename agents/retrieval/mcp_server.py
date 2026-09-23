"""
Retrieval agent exposed over the Model Context Protocol.

The Orchestrator launches this as an MCP client and calls its tools.
It is not started manually and has no port.
"""
import sys
sys.path.insert(0, ".")

from mcp.server.fastmcp import FastMCP
from agents.retrieval.search import Retriever

mcp = FastMCP("cinemate-retrieval")

# Loaded once when the server starts, reused for every call
retriever = Retriever(verbose=False)


@mcp.tool()
def search_movies(
    query: str,
    max_runtime: int = 0,
    min_year: int = 0,
    genres: str = "",
    max_age_rating: str = "",
    variants: str = "",
) -> list:
    """
    Search the film corpus using hybrid retrieval.

    query: what the user is looking for, described in words
    max_runtime: maximum length in minutes, 0 means no limit
    min_year: earliest release year, 0 means no limit
    genres: comma separated genre names, empty means any
    max_age_rating: G, PG, PG-13 or R. Empty means no limit
    variants: comma separated rewrites of the query, empty means none
    """
    filters = {}
    if max_runtime > 0:
        filters["max_runtime"] = max_runtime
    if min_year > 0:
        filters["min_year"] = min_year
    if genres:
        filters["genres"] = [g.strip() for g in genres.split(",") if g.strip()]
    if max_age_rating:
        filters["max_age_rating"] = max_age_rating

    variant_list = [v.strip() for v in variants.split(",") if v.strip()]

    return retriever.search(
        query, filters=filters, method="full", variants=variant_list
    )


@mcp.tool()
def search_with_relaxation(
    query: str,
    max_runtime: int = 0,
    min_year: int = 0,
    genres: str = "",
) -> dict:
    """
    Search, and if nothing matches, drop the narrowest filter and retry.

    Returns the results plus a list of which filters were dropped, so
    the user can be told honestly.
    """
    filters = {}
    if max_runtime > 0:
        filters["max_runtime"] = max_runtime
    if min_year > 0:
        filters["min_year"] = min_year
    if genres:
        filters["genres"] = [g.strip() for g in genres.split(",") if g.strip()]

    relaxed = []

    # Drop filters in order of how narrow they usually are
    for key in [None, "max_runtime", "min_year", "genres"]:
        if key:
            if key not in filters:
                continue
            filters.pop(key)
            relaxed.append(key)

        results = retriever.search(query, filters=filters, method="full")
        if results:
            return {"results": results, "relaxed_filters": relaxed}

    return {"results": [], "relaxed_filters": relaxed}


@mcp.tool()
def get_movie_details(doc_id: str) -> dict:
    """Fetch the full record for one film by its document id, e.g. m412."""
    try:
        movie_id = int(doc_id.lstrip("m"))
    except ValueError:
        return {"error": "invalid doc_id"}

    records = retriever.hydrate([(movie_id, 1.0)])
    return records[0] if records else {"error": "not found"}


if __name__ == "__main__":
    mcp.run()