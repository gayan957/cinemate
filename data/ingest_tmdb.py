"""
Fetch movies and reviews from TMDB and load them into Postgres.

Usage:
    python data/ingest_tmdb.py --pages 5      # small test, ~100 films
    python data/ingest_tmdb.py --pages 150    # full run, ~3000 films

Safe to run more than once. Existing films are skipped, not duplicated.
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
    DATABASE_URL, TMDB_API_KEY, TMDB_BASE, TMDB_DELAY,
    EMBEDDING_MODEL, MAX_REVIEWS_PER_MOVIE, CHUNK_SIZE, CHUNK_OVERLAP,
)


# ==================================================================
# TMDB requests
# ==================================================================
def tmdb_get(path, **params):
    """One GET against TMDB, with the key attached and a polite pause."""
    params["api_key"] = TMDB_API_KEY
    response = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=20)
    response.raise_for_status()
    time.sleep(TMDB_DELAY)
    return response.json()


def discover_movie_ids(pages):
    """Collect movie ids, most popular first. 20 per page."""
    ids = []
    for page in range(1, pages + 1):
        try:
            data = tmdb_get(
                "/discover/movie",
                sort_by="popularity.desc",
                include_adult="false",
                page=page,
            )
        except requests.RequestException as e:
            print(f"  page {page} failed: {e}")
            continue

        ids.extend(m["id"] for m in data.get("results", []))
        if page % 10 == 0:
            print(f"  discovered {len(ids)} ids ({page}/{pages} pages)")

    return list(dict.fromkeys(ids))          # de-duplicate, keep order


def movie_details(tmdb_id):
    """Everything about one film in a single request."""
    return tmdb_get(
        f"/movie/{tmdb_id}",
        append_to_response="credits,keywords,release_dates,reviews",
    )


# ==================================================================
# Pulling fields out of the TMDB response
# ==================================================================
def get_age_rating(data):
    """US certification such as PG-13. Returns NR when absent."""
    for entry in data.get("release_dates", {}).get("results", []):
        if entry.get("iso_3166_1") == "US":
            for release in entry.get("release_dates", []):
                cert = (release.get("certification") or "").strip()
                if cert:
                    return cert
    return "NR"


def get_director(data):
    for person in data.get("credits", {}).get("crew", []):
        if person.get("job") == "Director":
            return person.get("name")
    return None


def get_country(data):
    countries = data.get("production_countries") or []
    return countries[0].get("iso_3166_1") if countries else None


# ==================================================================
# Writing to the database
# ==================================================================
def insert_movie(cur, data):
    """Insert one film. Returns its id, or None if it already existed."""
    release = data.get("release_date") or None
    year = int(release[:4]) if release else None

    cur.execute(
        """
        INSERT INTO movies (
            tmdb_id, title, original_title, year, release_date, runtime,
            genres, age_rating, country, language, popularity,
            vote_average, vote_count, overview, tagline, keywords,
            cast_names, director, poster_path
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        ON CONFLICT (tmdb_id) DO NOTHING
        RETURNING id
        """,
        (
            data["id"],
            data.get("title"),
            data.get("original_title"),
            year,
            release,
            data.get("runtime"),
            [g["name"] for g in data.get("genres", [])],
            get_age_rating(data),
            get_country(data),
            data.get("original_language"),
            data.get("popularity"),
            data.get("vote_average"),
            data.get("vote_count"),
            data.get("overview"),
            data.get("tagline"),
            [k["name"] for k in data.get("keywords", {}).get("keywords", [])],
            [c["name"] for c in data.get("credits", {}).get("cast", [])[:10]],
            get_director(data),
            data.get("poster_path"),
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


def build_chunks(data, review_texts):
    """
    One film becomes several chunks:
      overview  - the plot description
      metadata  - title, genres, keywords, cast, director
      review    - one or more per review
    """
    chunks = []

    overview = data.get("overview") or ""
    if overview:
        parts = [data.get("title") or "", data.get("tagline") or "", overview]
        chunks.append(("overview", " ".join(p for p in parts if p)))

    meta_parts = [
        data.get("title") or "",
        " ".join(g["name"] for g in data.get("genres", [])),
        " ".join(k["name"] for k in data.get("keywords", {}).get("keywords", [])),
        " ".join(c["name"] for c in data.get("credits", {}).get("cast", [])[:6]),
        get_director(data) or "",
    ]
    metadata = " ".join(p for p in meta_parts if p).strip()
    if metadata:
        chunks.append(("metadata", metadata))

    for text in review_texts:
        for piece in split_long_text(text):
            chunks.append(("review", piece))

    return chunks


# ==================================================================
# Main
# ==================================================================
def main(pages, batch_size):
    if not TMDB_API_KEY:
        sys.exit("TMDB_API_KEY is missing from .env")
    if not DATABASE_URL:
        sys.exit("DATABASE_URL is missing from .env")

    print("Loading the embedding model...")
    embedder = SentenceTransformer(EMBEDDING_MODEL)

    print(f"Discovering films across {pages} pages...")
    movie_ids = discover_movie_ids(pages)
    print(f"Found {len(movie_ids)} unique films\n")

    pending = []                 # (movie_id, chunk_type, content)
    added = skipped = failed = 0

    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)    # lets psycopg send numpy arrays as vectors

        with conn.cursor() as cur:
            for n, tmdb_id in enumerate(movie_ids, 1):
                try:
                    data = movie_details(tmdb_id)
                except requests.RequestException as e:
                    print(f"  [{n}] film {tmdb_id} failed: {e}")
                    failed += 1
                    continue

                movie_id = insert_movie(cur, data)
                if movie_id is None:
                    skipped += 1
                    continue

                review_texts = insert_reviews(cur, movie_id, data)
                for chunk_type, content in build_chunks(data, review_texts):
                    pending.append((movie_id, chunk_type, content))

                added += 1

                if n % 25 == 0:
                    conn.commit()
                    print(f"  [{n}/{len(movie_ids)}] added {added}, "
                          f"skipped {skipped}, failed {failed}, "
                          f"chunks queued {len(pending)}")

            conn.commit()
            print(f"\nFilms added: {added}   already present: {skipped}   "
                  f"failed: {failed}")

            if not pending:
                print("No new chunks to embed.")
                return

            print(f"\nEmbedding {len(pending)} chunks...")
            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]

                vectors = embedder.encode(
                    [c[2] for c in batch],
                    batch_size=32,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

                for (movie_id, chunk_type, content), vector in zip(batch, vectors):
                    cur.execute(
                        "INSERT INTO chunks (movie_id, chunk_type, content, embedding) "
                        "VALUES (%s,%s,%s,%s)",
                        (movie_id, chunk_type, content, np.asarray(vector)),
                    )

                conn.commit()
                done = min(start + batch_size, len(pending))
                print(f"  embedded {done}/{len(pending)}")

            cur.execute("SELECT count(*) FROM movies")
            n_movies = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM chunks")
            n_chunks = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM reviews")
            n_reviews = cur.fetchone()[0]

    print(f"\nDone.")
    print(f"  films   : {n_movies}")
    print(f"  reviews : {n_reviews}")
    print(f"  chunks  : {n_chunks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5,
                        help="TMDB pages to fetch, 20 films per page")
    parser.add_argument("--batch", type=int, default=256,
                        help="chunks embedded per database batch")
    args = parser.parse_args()

    main(args.pages, args.batch)