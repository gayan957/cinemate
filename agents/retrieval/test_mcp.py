import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


def find_server_script() -> Path:
    # 1. Path given on the command line
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).resolve()
        if not p.exists():
            sys.exit(f"Server file not found: {p}")
        return p

    # 2. Auto-detect a FastMCP server in this folder
    candidates = []
    for p in HERE.glob("*.py"):
        if p.name == Path(__file__).name:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "FastMCP" in text or ".run(" in text and "mcp" in text.lower():
            candidates.append(p)

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        sys.exit(f"No MCP server file found in {HERE}. "
                 f"Run: python {Path(__file__).name} <path/to/server.py>")
    names = "\n  ".join(c.name for c in candidates)
    sys.exit(f"Several possible server files found:\n  {names}\n"
             f"Run: python {Path(__file__).name} <path/to/server.py>")


SERVER_SCRIPT = find_server_script()

params = StdioServerParameters(
    command=sys.executable,
    args=[str(SERVER_SCRIPT)],
    env={**os.environ, "HF_HUB_OFFLINE": "1"},
)


def parse_result(result):
    if result.isError:
        msg = result.content[0].text if result.content else "Unknown tool error"
        raise RuntimeError(msg)

    if result.structuredContent is not None:
        data = result.structuredContent
        return data.get("result", data) if isinstance(data, dict) else data

    items = []
    for c in result.content:
        text = getattr(c, "text", "")
        if not text.strip():
            continue
        try:
            items.append(json.loads(text))
        except json.JSONDecodeError:
            items.append(text)
    return items[0] if len(items) == 1 else items


async def main():
    print(f"Starting server: {SERVER_SCRIPT}")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools this server offers:")
            for t in tools.tools:
                print(f"  - {t.name}")

            search_tool = next((t for t in tools.tools if t.name == "search_movies"), None)
            if search_tool is None:
                print("search_movies not found on server")
                return

            # Build arguments from the tool's schema
            props = search_tool.inputSchema.get("properties", {})
            required = search_tool.inputSchema.get("required", [])
            print("search_movies parameters:", list(props.keys()), "required:", required)

            first_param = required[0] if required else next(iter(props), "query")
            args = {first_param: "space adventure"}

            print(f"\nCalling search_movies with {args} ...")
            result = await session.call_tool("search_movies", args)

            try:
                films = parse_result(result)
            except RuntimeError as e:
                print("Tool failed:", e)
                return

            print(json.dumps(films, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())