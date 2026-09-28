# TV series support

CineMate now recommends TV series as well as films. A user can ask for
either one, or say nothing and get the best match from both.

> "a gripping crime tv series" → *Columbo*, *Law & Order*, *C.I.D.*
> "a hopeful space film under two hours" → films only
> "a feel-good story about friendship" → films and series together

## Design in one paragraph

Films and series share **one table** (`movies`) with a `media_type`
column set to `movie` or `tv`. Reviews, chunks, embeddings and all six
retrieval methods work unchanged for both types. The table keeps its name
and `doc_id`s keep the `m<id>` form, so the Guardian, the Analysis agent
and the evaluation scripts needed no changes. The type is a
structured filter applied in SQL, like runtime and year.

## What each field means for a series

| Column | Film | TV series |
|---|---|---|
| `title` | title | name |
| `year`, `release_date` | release | first air date |
| `runtime` | film length | **one episode's** length |
| `age_rating` | US certificate (PG-13) | US TV rating (TV-14) |
| `director` | director | usually empty |
| `creator` | — | created by |
| `seasons`, `episodes` | — | counts |
| `status` | — | Ended, Returning Series… |
| `network` | — | first network, e.g. AMC |
| `country` | first production country | first origin country |

## Changes by component

### Database (`data/schema.sql`)
- New columns: `media_type`, `creator`, `seasons`, `episodes`, `status` and `network`.
- TMDB numbers films and series separately: movie 1396 is *Mirror* and
  tv 1396 is *Breaking Bad*. The unique key is now `(media_type, tmdb_id)`
  instead of `tmdb_id` alone.
- The file includes `ALTER TABLE ... IF NOT EXISTS` statements, so running it
  again upgrades an existing database without losing data. Existing rows
  become `movie`.

### Ingestion (`data/ingest_tmdb.py`)
- New `--type movie|tv|both` flag. The default is `both`. `--pages` applies to each type.
- Series come from `/discover/tv` and `/tv/{id}`.
- News, Soap and Talk shows are excluded, because they otherwise dominate
  TMDB's popularity list.
- Some TMDB TV genres combine two genres. They are split into the genre names
  films use, so one genre filter works for both types:
  - Action & Adventure → Action, Adventure
  - Sci-Fi & Fantasy → Science Fiction, Fantasy
  - War & Politics → War, Politics
- Episode length comes from `episode_run_time`. When that is empty, which is
  common, it comes from the most recent episode.
- The metadata chunk now starts with `TV series show` or `film movie`.
  This lets keyword and vector search match those words.

### Retrieval (`agents/retrieval/search.py`, `mcp_server.py`)
- `apply_filters` accepts `media_type`.
- Age limits cover TV ratings. Each TV rating is allowed alongside its nearest film rating:

  | Limit (film) | Also allows |
  |---|---|
  | G | TV-Y, TV-Y7, TV-G |
  | PG | + TV-PG |
  | PG-13 | + TV-14 |
  | R | + TV-MA |

- `search_movies` and `search_with_relaxation` take a `media_type` argument.
  An empty value means both types.
- **Safety fix.** `search_with_relaxation` previously never received
  `max_age_rating`. When a search fell back to relaxation, an under-13
  account could be shown R-rated titles. It now receives the age limit.
  Relaxation never drops the age limit or `media_type`.

### Orchestrator
- **Planner prompt:** the plan has a `filters.media_type` field.
  - It is `"tv"` for "TV show", "series", "sitcom", "binge" and similar, and
    `"movie"` for "film" or "movie". Otherwise it is null.
  - For a series, `max_runtime` is the episode length.
  - The prompt has a new TV example.
- **Rule-based fallback:** detects the same words with regular expressions.
  "show me a film" is not treated as TV. A request that mentions both types
  searches both.
- **Answer step:**
  - The LLM is told when a title is a series, with its seasons, episode length
    and creator.
  - The answer prompt asks it to say which titles are series.
  - Each recommendation carries `media_type`.

### Frontend
- The recommendations table has a Film / TV series column.
- The placeholder text and button label now cover series too.

### Also fixed while testing: empty LLM replies
`openai/gpt-oss-120b` is a reasoning model. At its default reasoning effort,
it sometimes used the whole `max_tokens` budget on hidden reasoning and
returned nothing:
- **Planner:** Groq reported `json_validate_failed`. This happened on 2 of 10
  calls at `max_tokens=400`.
- **Answer step:** an **empty answer** was returned with no error. This
  happened about 1 time in 4 and failed `test_system.py`.

Both calls now use `reasoning_effort="low"` and `max_tokens=1024`.
The planner then succeeded on 10 of 10 calls using about 150 tokens each,
and the answer step on 12 of 12. An empty answer now also triggers the
fallback list, instead of reaching the user as a blank reply.
**If `LLM_MODEL` is changed to a model that does not reason, remove
`reasoning_effort`**, because Groq rejects it for those models.

## Setting it up

```bash
psql "$DATABASE_URL" -f data/schema.sql          # upgrade the schema
python data/ingest_tmdb.py --pages 5 --type tv   # ~100 series
python data/inspect_db.py                        # films / series counts
```

## Verified on 27 September 2026

The database was upgraded in place: the 109 existing films were kept, and
100 series and 540 chunks were added.

- **Retrieval:**
  - The `tv` and `movie` filters return only that type.
  - A PG limit returns only TV-PG and below.
  - Episode-length and mapped-genre filters work.
- **Planner (LLM):** "crime tv series" gives `tv`. "funny show with half-hour
  episodes" gives `tv` with 30 minutes. A request that names no type gives null.
- **Fallback planner:** gets the same queries right, including "show me a heist film", which gives `movie`.
- **`test_system.py`:** 16 of 16 checks pass, including the new TV series check.

## Known limitations

- **Episode length can be wrong.** It comes from the latest episode, so a long
  finale gives a misleading figure. *Stranger Things* shows 129 minutes.
- **Unrated titles are hidden from minors.** 15 of the 100 series have no US
  rating (`NR`), so accounts under 17 never see them. Films already behave
  this way.
- **Older films lack the type words.** The 109 films ingested before this
  change have metadata chunks without `film movie` in them. The type filter
  is unaffected, but a keyword match on the word "movie" favours newly
  ingested films slightly. Re-ingesting fixes it.
- **The answer and the table can list different titles.** The answer text
  chooses the best three of five retrieved titles, while the recommendations
  table always shows the top three. This was already the case before TV support.
