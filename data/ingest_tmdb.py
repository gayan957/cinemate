"""
Fetch movies, TV series and their reviews from TMDB and load them
into Postgres.

Usage:
    python data/ingest_tmdb.py                        # MOVIE_PAGES and TV_PAGES from config
    python data/ingest_tmdb.py --pages 5              # small test, ~100 of each
    python data/ingest_tmdb.py --pages 5 --type tv    # TV series only
    python data/ingest_tmdb.py --reset                # empty the title data first

Safe to run more than once. Existing titles are skipped, not duplicated.
Safe to stop with Ctrl+C: each title is saved together with its chunks,
so running again carries on where it stopped.
"""
import argparse
import sys
import time

import numpy as np
import psycopg
import requests
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

sys.path.insert(0, ".")
from shared.config import (
    DATABASE_URL, TMDB_API_KEY, TMDB_BASE, TMDB_DELAY, MOVIE_PAGES, TV_PAGES,
    EMBEDDING_MODEL, MAX_REVIEWS_PER_MOVIE, CHUNK_SIZE, CHUNK_OVERLAP,
)


# ==================================================================
# TMDB requests
# ==================================================================
RETRIES = 4
MAX_TMDB_PAGES = 500          # TMDB refuses any page above this


def tmdb_get(path, **params):
    """
    One GET against TMDB, with the key attached and a polite pause.

    Rate limits, server errors and timeouts are retried with a growing
    wait. Over a run of thousands of requests a few always fail once.
    """
    params["api_key"] = TMDB_API_KEY

    for attempt in range(1, RETRIES + 1):
        try:
            response = requests.get(
                f"{TMDB_BASE}{path}", params=params, timeout=20
            )
            if response.status_code == 429 or response.status_code >= 500:
                wait = int(response.headers.get("Retry-After", 0)) or 2 ** attempt
                raise requests.HTTPError(
                    f"{response.status_code}, retrying in {wait}s",
                    response=response,
                )
            response.raise_for_status()
            time.sleep(TMDB_DELAY)
            return response.json()

        except (requests.ConnectionError, requests.Timeout,
                requests.HTTPError) as e:
            status = getattr(e.response, "status_code", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == RETRIES:
                raise
            time.sleep(2 ** attempt)


# TV genres that are not stories people ask to be recommended:
# News, Soap and Talk. They dominate TMDB's popularity list otherwise.
TV_EXCLUDED_GENRES = "10763|10766|10767"


def discover_ids(media, pages):
    """Collect movie or tv ids, most popular first. 20 per page."""
    extra = {"without_genres": TV_EXCLUDED_GENRES} if media == "tv" else {}

    if pages > MAX_TMDB_PAGES:
        print(f"  TMDB serves at most {MAX_TMDB_PAGES} pages, "
              f"so {pages} becomes {MAX_TMDB_PAGES}")
        pages = MAX_TMDB_PAGES

    ids = []
    for page in range(1, pages + 1):
        try:
            data = tmdb_get(
                f"/discover/{media}",
                sort_by="popularity.desc",
                include_adult="false",
                page=page,
                **extra,
            )
        except requests.RequestException as e:
            print(f"  page {page} failed: {e}")
            continue

        ids.extend(m["id"] for m in data.get("results", []))
        if page % 10 == 0:
            print(f"  discovered {len(ids)} ids ({page}/{pages} pages)")

    return list(dict.fromkeys(ids))          # de-duplicate, keep order


def details(media, tmdb_id):
    """Everything about one film or series in a single request."""
    ratings = "content_ratings" if media == "tv" else "release_dates"
    return _strip_nul(tmdb_get(
        f"/{media}/{tmdb_id}",
        append_to_response=f"credits,keywords,{ratings},reviews",
    ))


def _strip_nul(value):
    """
    Postgres rejects the NUL character in text, and a few TMDB reviews
    contain one. Remove it everywhere before anything is saved.
    """
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_nul(v) for k, v in value.items()}
    return value


# ==================================================================
# Pulling fields out of the TMDB response
#
# TMDB describes films and series with different field names. These
# helpers read either, so the rest of the script treats them the same.
# ==================================================================
def get_title(data):
    return data.get("title") or data.get("name")


def get_release(data):
    """Release date for a film, first air date for a series."""
    return data.get("release_date") or data.get("first_air_date") or None


def get_runtime(data):
    """Film length, or typical episode length for a series."""
    if data.get("runtime"):
        return data["runtime"]

    # episode_run_time is often empty for series, so fall back to the
    # most recent episode
    episode_times = data.get("episode_run_time") or []
    if episode_times:
        return episode_times[0]
    return (data.get("last_episode_to_air") or {}).get("runtime")


# The planner and the genre filter use film genre names. TMDB merges
# some TV genres, so split those into the film names.
TV_GENRE_MAP = {
    "Action & Adventure": ["Action", "Adventure"],
    "Sci-Fi & Fantasy": ["Science Fiction", "Fantasy"],
    "War & Politics": ["War", "Politics"],
}


def get_genres(data):
    genres = []
    for g in data.get("genres", []):
        for name in TV_GENRE_MAP.get(g["name"], [g["name"]]):
            if name not in genres:
                genres.append(name)
    return genres


def get_keywords(data):
    """Films list keywords under 'keywords', series under 'results'."""
    block = data.get("keywords", {})
    return [k["name"] for k in block.get("keywords") or block.get("results") or []]


def get_age_rating(data):
    """US certification such as PG-13 or TV-14. Returns NR when absent."""
    for entry in data.get("release_dates", {}).get("results", []):
        if entry.get("iso_3166_1") == "US":
            for release in entry.get("release_dates", []):
                cert = (release.get("certification") or "").strip()
                if cert:
                    return cert

    for entry in data.get("content_ratings", {}).get("results", []):
        if entry.get("iso_3166_1") == "US":
            cert = (entry.get("rating") or "").strip()
            if cert:
                return cert

    return "NR"


def get_director(data):
    for person in data.get("credits", {}).get("crew", []):
        if person.get("job") == "Director":
            return person.get("name")
    return None


def get_creator(data):
    """Series only. Several creators are joined with commas."""
    names = [p.get("name") for p in data.get("created_by") or [] if p.get("name")]
    return ", ".join(names) or None


def get_country(data):
    # Series carry a plain list of codes, which is more reliable for TV
    origin = data.get("origin_country") or []
    if origin:
        return origin[0]

    countries = data.get("production_countries") or []
    return countries[0].get("iso_3166_1") if countries else None


def get_network(data):
    networks = data.get("networks") or []
    return networks[0].get("name") if networks else None


# ==================================================================
# Writing to the database
# ==================================================================
def insert_movie(cur, data, media="movie"):
    """Insert one film or series. Returns its id, or None if it already existed."""
    release = get_release(data)
    year = int(release[:4]) if release else None
    is_tv = media == "tv"

    cur.execute(
        """
        INSERT INTO movies (
            media_type, tmdb_id, title, original_title, year, release_date,
            runtime, genres, age_rating, country, language, popularity,
            vote_average, vote_count, overview, tagline, keywords,
            cast_names, director, poster_path,
            creator, seasons, episodes, status, network
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s
        )
        ON CONFLICT (media_type, tmdb_id) DO NOTHING
        RETURNING id
        """,
        (
            media,
            data["id"],
            get_title(data),
            data.get("original_title") or data.get("original_name"),
            year,
            release,
            get_runtime(data),
            get_genres(data),
            get_age_rating(data),
            get_country(data),
            data.get("original_language"),
            data.get("popularity"),
            data.get("vote_average"),
            data.get("vote_count"),
            data.get("overview"),
            data.get("tagline"),
            get_keywords(data),
            [c["name"] for c in data.get("credits", {}).get("cast", [])[:10]],
            get_director(data),
            data.get("poster_path"),
            get_creator(data) if is_tv else None,
            data.get("number_of_seasons") if is_tv else None,
            data.get("number_of_episodes") if is_tv else None,
            data.get("status") if is_tv else None,
            get_network(data) if is_tv else None,
        ),
    )
    row = cur.fetchone()
    return row[0] if row else None


def insert_reviews(cur, movie_id, data):
    """Store reviews and return their text for chunking."""
    texts = []
    reviews = data.get("reviews", {}).get("results", [])

    for review in reviews[:MAX_REVIEWS_PER_MOVIE]:
        content = (review.get("content") or "").strip()
        if len(content) < 50:
            continue

        cur.execute(
            "INSERT INTO reviews (movie_id, author, content, rating, source) "
            "VALUES (%s,%s,%s,%s,%s)",
            (
                movie_id,
                review.get("author"),
                content,
                (review.get("author_details") or {}).get("rating"),
                "tmdb",
            ),
        )
        texts.append(content)

    return texts


# ==================================================================
# Turning a film into searchable chunks
# ==================================================================
def split_long_text(text):
    """Cut a long review into overlapping pieces so retrieval stays precise."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    pieces, step = [], CHUNK_SIZE - CHUNK_OVERLAP
    for start in range(0, len(text), step):
        piece = text[start:start + CHUNK_SIZE].strip()
        if len(piece) > 100:
            pieces.append(piece)
    return pieces


def build_chunks(data, review_texts, media="movie"):
    """
    One film or series becomes several chunks:
      overview  - the plot description
      metadata  - type, title, genres, keywords, cast, director or creator
      review    - one or more per review
    """
    chunks = []
    title = get_title(data) or ""

    overview = data.get("overview") or ""
    if overview:
        parts = [title, data.get("tagline") or "", overview]
        chunks.append(("overview", " ".join(p for p in parts if p)))

    # The type words let keyword and vector search match "a tv show"
    # or "a series" against the right titles
    kind = "TV series show" if media == "tv" else "film movie"
    meta_parts = [
        kind,
        title,
        " ".join(get_genres(data)),
        " ".join(get_keywords(data)),
        " ".join(c["name"] for c in data.get("credits", {}).get("cast", [])[:6]),
        get_director(data) or "",
        get_creator(data) or "",
        get_network(data) or "",
    ]
    metadata = " ".join(p for p in meta_parts if p).strip()
    if metadata:
        chunks.append(("metadata", metadata))

    for text in review_texts:
        for piece in split_long_text(text):
            chunks.append(("review", piece))

    return chunks


# ==================================================================
# Saving chunks
# ==================================================================
def save_chunks(cur, embedder, pending):
    """Embed the queued chunks and insert them. Empties the queue."""
    if not pending:
        return

    vectors = embedder.encode(
        [c[2] for c in pending],
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    for (movie_id, chunk_type, content), vector in zip(pending, vectors):
        cur.execute(
            "INSERT INTO chunks (movie_id, chunk_type, content, embedding) "
            "VALUES (%s,%s,%s,%s)",
            (movie_id, chunk_type, content, np.asarray(vector)),
        )

    pending.clear()


def reset(cur):
    """Remove every title, review and chunk. Accounts and logs are kept."""
    cur.execute("TRUNCATE movies, reviews, chunks RESTART IDENTITY")
    print("Emptied movies, reviews and chunks. Users and logs kept.\n")


def remove_orphans(cur):
    """
    Delete titles that have no chunks.

    Every title gets at least a metadata chunk, so a title without any
    was left behind by an older, interrupted run. Search can never find
    it, and it would be skipped as "already present" forever.
    """
    cur.execute(
        "DELETE FROM movies m "
        "WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.movie_id = m.id)"
    )
    if cur.rowcount:
        print(f"Removed {cur.rowcount} titles left without chunks by an "
              f"interrupted run. They will be fetched again.\n")


# ==================================================================
# Main
# ==================================================================
COMMIT_EVERY = 25              # titles per save


def main(pages, media_types, clear=False):
    if not TMDB_API_KEY:
        sys.exit("TMDB_API_KEY is missing from .env")
    if not DATABASE_URL:
        sys.exit("DATABASE_URL is missing from .env")

    print("Loading the embedding model...")
    embedder = SentenceTransformer(EMBEDDING_MODEL)

    pending = []                 # (movie_id, chunk_type, content)
    added = skipped = failed = 0

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)    # lets psycopg send numpy arrays as vectors

        with conn.cursor() as cur:
            if clear:
                reset(cur)
            remove_orphans(cur)
            conn.commit()

            for media in media_types:
                label = "series" if media == "tv" else "films"
                n_pages = pages or (TV_PAGES if media == "tv" else MOVIE_PAGES)

                print(f"Discovering {label} across {n_pages} pages...")
                tmdb_ids = discover_ids(media, n_pages)
                print(f"Found {len(tmdb_ids)} unique {label}\n")

                # Skip titles already saved without downloading them again,
                # so a resumed run gets back to new titles quickly
                cur.execute(
                    "SELECT tmdb_id FROM movies WHERE media_type = %s", (media,)
                )
                have = {r[0] for r in cur.fetchall()}
                if have:
                    print(f"  {len(have & set(tmdb_ids))} of these are "
                          f"already saved and will be skipped")

                for n, tmdb_id in enumerate(tmdb_ids, 1):
                    if tmdb_id in have:
                        skipped += 1
                        continue

                    try:
                        data = details(media, tmdb_id)
                    except requests.RequestException as e:
                        print(f"  [{n}] {media} {tmdb_id} failed: {e}")
                        failed += 1
                        continue

                    # A savepoint, so one bad title is skipped instead of
                    # breaking every title after it. Plain SQL on purpose:
                    # conn.transaction() would commit each title on its
                    # own, before its chunks exist.
                    cur.execute("SAVEPOINT title")
                    try:
                        movie_id = insert_movie(cur, data, media)
                        review_texts = (insert_reviews(cur, movie_id, data)
                                        if movie_id else [])
                        cur.execute("RELEASE SAVEPOINT title")
                    except psycopg.Error as e:
                        cur.execute("ROLLBACK TO SAVEPOINT title")
                        print(f"  [{n}] {media} {tmdb_id} not saved: {e}")
                        failed += 1
                        continue

                    if movie_id is None:
                        skipped += 1
                        continue

                    for chunk_type, content in build_chunks(
                        data, review_texts, media
                    ):
                        pending.append((movie_id, chunk_type, content))

                    added += 1

                    # Titles and their chunks are committed together, so
                    # stopping the run never leaves a title unsearchable
                    if n % COMMIT_EVERY == 0:
                        save_chunks(cur, embedder, pending)
                        conn.commit()
                        print(f"  [{n}/{len(tmdb_ids)}] added {added}, "
                              f"skipped {skipped}, failed {failed}")

                save_chunks(cur, embedder, pending)
                conn.commit()

            cur.execute("SELECT count(*) FROM movies WHERE media_type = 'movie'")
            n_movies = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM movies WHERE media_type = 'tv'")
            n_series = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM chunks")
            n_chunks = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM reviews")
            n_reviews = cur.fetchone()[0]

    print(f"\nTitles added: {added}   already present: {skipped}   "
          f"failed: {failed}")
    print(f"\nDone.")
    print(f"  films   : {n_movies}")
    print(f"  series  : {n_series}")
    print(f"  reviews : {n_reviews}")
    print(f"  chunks  : {n_chunks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=None,
                        help="TMDB pages to fetch per type, 20 titles per page. "
                             "Default: MOVIE_PAGES and TV_PAGES in config")
    parser.add_argument("--type", choices=["movie", "tv", "both"],
                        default="both", help="what to ingest")
    parser.add_argument("--reset", action="store_true",
                        help="delete all titles, reviews and chunks first "
                             "(accounts and logs are kept)")
    args = parser.parse_args()

    types = ["movie", "tv"] if args.type == "both" else [args.type]
    main(args.pages, types, clear=args.reset)
