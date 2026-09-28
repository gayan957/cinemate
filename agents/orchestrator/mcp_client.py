"""
Talks to the Retrieval agent over the Model Context Protocol.

The Orchestrator launches the retrieval server as a subprocess. That
is how MCP works: the client starts the server it wants to use.
"""
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, ".")
from shared.config import RETRIEVAL_SERVER


def _extract(result):
    """
    Pull the payload out of an MCP tool result.

    Newer MCP versions wrap a non-dict return value as {"result": ...},
    so unwrap that when present. Without structured content, a returned
    list arrives as one text block per item, so every block is read.
    """
    # Prefer structured content when the server provides it
    data = getattr(result, "structuredContent", None)

    if data is None:
        texts = [c.text for c in result.content or [] if hasattr(c, "text")]
        try:
            parsed = [json.loads(t) for t in texts]
        except json.JSONDecodeError:
            return None
        if not parsed:
            return None
        data = parsed[0] if len(parsed) == 1 else parsed

    # Unwrap {"result": [...]} but leave real dict payloads alone
    if isinstance(data, dict) and set(data.keys()) == {"result"}:
        return data["result"]

    return data


def _as_list(data):
    """
    Return the list inside any shape a list-returning tool can produce:
    a bare list, {"result": [...]}, or any other single-key dict wrapping
    a list. Returns [] if there isn't one.
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict) and len(data) == 1:
        (value,) = data.values()
        if isinstance(value, list):
            return value

    # A single film arrives as one object, not a list of one
    if isinstance(data, dict) and "doc_id" in data:
        return [data]

    return []


async def search(query, filters, variants=None, relax=True):
    """
    Search, with filter relaxation when nothing matches.

    Returns (films, relaxed_filters).
    """
    params = StdioServerParameters(
        command=sys.executable,
        args=[RETRIEVAL_SERVER],
    )

    arguments = {
        "query": query,
        "max_runtime": filters.get("max_runtime") or 0,
        "min_year": filters.get("min_year") or 0,
        "genres": ",".join(filters.get("genres") or []),
        "max_age_rating": filters.get("max_age_rating") or "",
        "variants": ",".join(variants or []),
        "media_type": filters.get("media_type") or "",
    }

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("search_movies", arguments)
            films = _as_list(_extract(result))

            if films or not relax:
                return films, []

            # STEP 67 — nothing matched, so relax the narrowest filters
            relaxed = await session.call_tool(
                "search_with_relaxation",
                {
                    "query": query,
                    "max_runtime": arguments["max_runtime"],
                    "min_year": arguments["min_year"],
                    "genres": arguments["genres"],
                    "max_age_rating": arguments["max_age_rating"],
                    "media_type": arguments["media_type"],
                },
            )
            # This tool really returns a dict, so it is not unwrapped
            data = _extract(relaxed)
            if isinstance(data, dict) and "results" in data:
                return data["results"], data.get("relaxed_filters", [])
            return [], []