"""
Inspect the CineMate database.

Usage:
    python data/inspect_db.py

Prints size, review coverage, data quality and country distribution.
Run this after the small test ingest and again after the full run.
"""
import sys

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, ".")
from shared.config import DATABASE_URL


def show(title):
    print(f"\n{'=' * 58}\n{title}\n{'=' * 58}")


def main():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:

            # ---------- counts ----------
            show("ROW COUNTS")
            for table in ["movies", "reviews", "chunks"]:
                cur.execute(f"SELECT count(*) AS n FROM {table}")
                print(f"  {table:<10} {cur.fetchone()['n']:>8,}")

            # ---------- size ----------
            show("DATABASE SIZE")
            cur.execute(
                "SELECT pg_size_pretty(pg_database_size(current_database())) AS size"
            )
            total = cur.fetchone()["size"]
            print(f"  total: {total}")

            cur.execute("SELECT count(*) AS n FROM movies")
            n_movies = cur.fetchone()["n"]

            cur.execute(
                "SELECT pg_database_size(current_database()) AS bytes"
            )
            raw = cur.fetchone()["bytes"]

            if n_movies:
                per_film = raw / n_movies
                print(f"  per film: {per_film / 1024:.1f} KB")
                print(f"  estimate for 3,000 films: "
                      f"{per_film * 3000 / (1024 ** 2):.0f} MB")

            show("SIZE BY TABLE")
            cur.execute("""
                SELECT relname AS table_name,
                       pg_size_pretty(pg_total_relation_size(relid)) AS size
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
            """)
            for row in cur.fetchall():
                print(f"  {row['table_name']:<12} {row['size']:>10}")

            # ---------- review coverage ----------
            show("REVIEW COVERAGE")
            cur.execute("""
                SELECT
                  (SELECT count(DISTINCT movie_id) FROM reviews) AS with_reviews,
                  (SELECT count(*) FROM movies) AS total
            """)
            row = cur.fetchone()
            with_reviews, total = row["with_reviews"], row["total"]
            pct = 100.0 * with_reviews / total if total else 0

            print(f"  films with at least one review: {with_reviews:,} / {total:,}")
            print(f"  coverage: {pct:.1f}%")

            if pct < 30:
                print("\n  LOW. Your Analysis agent has little to work with.")
                print("  Options: supplement from a licensed public dataset,")
                print("  or report the figure honestly and rely on metadata chunks.")
            elif pct < 50:
                print("\n  Workable. Report this figure in your report.")
            else:
                print("\n  Good coverage.")

            # ---------- chunk types ----------
            show("CHUNK TYPES")
            cur.execute("""
                SELECT chunk_type, count(*) AS n
                FROM chunks GROUP BY chunk_type ORDER BY n DESC
            """)
            for row in cur.fetchall():
                print(f"  {row['chunk_type']:<12} {row['n']:>8,}")

            cur.execute("SELECT count(*) AS n FROM chunks WHERE embedding IS NULL")
            missing = cur.fetchone()["n"]
            print(f"\n  chunks missing an embedding: {missing:,}")
            if missing:
                print("  PROBLEM: re-run ingestion for these.")

            # ---------- data quality ----------
            show("DATA QUALITY")
            checks = [
                ("no overview", "overview IS NULL OR overview = ''"),
                ("no age rating", "age_rating IS NULL OR age_rating = 'NR'"),
                ("no country", "country IS NULL"),
                ("no runtime", "runtime IS NULL OR runtime = 0"),
                ("no year", "year IS NULL OR year = 0"),
                ("no director", "director IS NULL"),
            ]
            for label, condition in checks:
                cur.execute(f"SELECT count(*) AS n FROM movies WHERE {condition}")
                n = cur.fetchone()["n"]
                pct = 100.0 * n / total if total else 0
                print(f"  {label:<16} {n:>6,}  ({pct:>5.1f}%)")

            # ---------- fairness baseline ----------
            show("COUNTRY DISTRIBUTION (corpus)")
            cur.execute("""
                SELECT COALESCE(country, 'unknown') AS country,
                       count(*) AS n,
                       round(100.0 * count(*) / SUM(count(*)) OVER (), 1) AS pct
                FROM movies
                GROUP BY country ORDER BY n DESC LIMIT 10
            """)
            for row in cur.fetchall():
                print(f"  {row['country']:<10} {row['n']:>6,}  ({row['pct']:>5}%)")

            print("\n  Keep these figures. Phase 9 compares them against")
            print("  the country distribution of your recommendations.")

            # ---------- sample ----------
            show("SAMPLE FILMS")
            cur.execute("""
                SELECT title, year, runtime, age_rating, country,
                       array_length(genres, 1) AS n_genres
                FROM movies ORDER BY popularity DESC NULLS LAST LIMIT 5
            """)
            for row in cur.fetchall():
                print(f"  {row['title'][:34]:<34} {row['year']}  "
                      f"{row['runtime']}min  {row['age_rating']:<6} "
                      f"{row['country'] or '??'}")

    print()


if __name__ == "__main__":
    main()