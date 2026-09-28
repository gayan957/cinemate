# Bug fixes — 27 September 2026

Three fixes to the Orchestrator and the frontend. No other agents changed.

## 1. Retrieval returned no results (`agents/orchestrator/mcp_client.py`)

**Symptom.** The Orchestrator logged
`retrieval returned <class 'dict'>, expected list` and every search came back empty.

**Root cause.** `search_movies` is declared `-> list`. With the installed
`mcp` version (1.30), FastMCP sends **no** `structuredContent` for a bare
`list` return type. Instead it sends **one text content block per list item**.
`_extract` only parsed `content[0]`, so it returned the first film as a
dict and dropped the rest.

Other `mcp` versions can wrap the same return value as `{"result": [...]}`,
either in `structuredContent` or in the text, so both cases have to be handled.

**Fix.**

- `_extract` now parses every text block. One block gives that value,
  several blocks give a list. It still prefers `structuredContent` when
  present and still unwraps `{"result": ...}`.
- New helper `_as_list(data)` returns the list from any of these shapes:
  - a bare list
  - `{"result": [...]}`
  - any other single-key dict wrapping a list
  - a single film object (a one-item list arrives as one block)

  Anything else gives `[]`.
- `search_movies` results go through `_as_list(_extract(...))`.
- `search_with_relaxation` really does return
  `{"results": [...], "relaxed_filters": [...]}`, so it is **not** unwrapped.
  The client checks for the `"results"` key and returns both values.

| Tool result as received | `_as_list(_extract(r))` |
|---|---|
| `structuredContent = [f1, f2]` | `[f1, f2]` |
| `structuredContent = {"result": [f1, f2]}` | `[f1, f2]` |
| `structuredContent = {"items": [f1, f2]}` | `[f1, f2]` |
| text blocks `f1`, `f2` (mcp 1.30) | `[f1, f2]` |
| a single text block `f1` | `[f1]` |
| no content | `[]` |

These were checked against a live FastMCP server running mcp 1.30.

## 2. Planner always fell back to rules (`agents/orchestrator/planner.py`)

**Symptom.** `planner fell back to rules: Expecting ',' delimiter`.
The LLM returned malformed JSON, so `fallback_plan` ran on every request
and the LLM's filters and variants were lost.

**Fix.** The Groq `chat.completions.create` call now passes
`response_format={"type": "json_object"}`, which makes the model return
valid JSON. JSON mode requires the word "JSON" in the prompt, and
`prompts/planner.txt` already contains it. `_parse_json` and the rule-based
fallback stay as a safety net for timeouts and rate limits.

**Follow-up.** JSON mode alone was not enough. `gpt-oss-120b` sometimes
spent all 400 tokens reasoning, and Groq then returned `json_validate_failed`
on 2 of 10 calls. The call now also sets `reasoning_effort="low"` and
`max_tokens=1024`, which gave 10 of 10 successes. The answer step had the
same problem and silently returned empty answers. See
[tv-series-support.md](tv-series-support.md#also-fixed-while-testing-empty-llm-replies).

## 3. Streamlit deprecation warning (`frontend/app.py`)

`st.dataframe(..., use_container_width=True)` is deprecated.
It is now `st.dataframe(..., width="stretch")`, which renders the same way.

## How to check

```bash
python run_all.py          # in one terminal
python test_system.py      # in another
```

Things to look for:

- "Normal query" passes "gave recommendations" and "used retrieval".
- The Orchestrator log no longer shows `retrieval returned <class 'dict'>`.
- The Orchestrator log no longer shows `planner fell back to rules: Expecting ...`.
- Streamlit no longer prints the `use_container_width` warning.
