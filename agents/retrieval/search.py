"""
CineMate retrieval engine.

Six search methods over the local Postgres corpus, each callable
separately so the Phase 9 evaluation can compare them.

Every method returns a list of (movie_id, score), best first.
"""
import sys
from collections import defaultdict

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

sys.path.insert(0, ".")
from shared.config import (
    DATABASE_URL, EMBEDDING_MODEL, RERANKER_MODEL,
    CANDIDATES, FINAL_K, RRF_K, MMR_LAMBDA,
)


class Retriever:
    """Loads the corpus and the models once, then answers many queries."""

    def __init__(self, verbose=True):
        self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        register_vector(self.conn)

        if verbose:
            print("Loading embedding model...")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)

        if verbose:
            print("Loading re-ranking model...")
        self.reranker = CrossEncoder(RERANKER_MODEL)

        self._load_bm25(verbose)

    # ==============================================================
    # BM25 needs the text in memory, so load it once at startup
    # ==============================================================
    def _load_bm25(self, verbose=True):
        with self.conn.cursor() as cur:
            cur.execute("SELECT id, movie_id, content FROM chunks ORDER BY id")
            rows = cur.fetchall()

        self.chunk_movie = [r["movie_id"] for r in rows]
        self.chunk_text = [r["content"] for r in rows]

        tokenised = [self._tokenise(t) for t in self.chunk_text]
        self.bm25 = BM25Okapi(tokenised)

        if verbose:
            print(f"BM25 index built over {len(rows):,} chunks")

    @staticmethod
    def _tokenise(text):
        """Lowercase and split on whitespace. Simple on purpose."""
        return text.lower().split()

    @staticmethod
    def _collapse(pairs, k):
        """
        Chunks become films.

        One film may match on several chunks. Take its best chunk score,
        then rank films by that.
        """
        best = {}
        for movie_id, score in pairs:
            if score > best.get(movie_id, float("-inf")):
                best[movie_id] = score
        return sorted(best.items(), key=lambda x: x[1], reverse=True)[:k]

    # ==============================================================
    # STEP 38 — Method 1: BM25 keyword search
    # ==============================================================
    def bm25_search(self, query, k=CANDIDATES):
        """
        Scores every chunk by keyword overlap.

        Strong on exact names. Weak on mood words that never appear
        literally in the text.
        """
        scores = self.bm25.get_scores(self._tokenise(query))

        # Look at more chunks than we need, since many belong to one film
        top_idx = np.argsort(scores)[::-1][: k * 5]
        pairs = [
            (self.chunk_movie[i], float(scores[i]))
            for i in top_idx if scores[i] > 0
        ]
        return self._collapse(pairs, k)

    # ==============================================================
    # STEP 39 — Method 2: Postgres full-text search
    # ==============================================================
    def fulltext_search(self, query, k=CANDIDATES):
        """
        Uses the tsv column and GIN index built by schema.sql.

        A second sparse method. Included so the evaluation can show
        that not all keyword methods behave the same.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT movie_id,
                       ts_rank(tsv, plainto_tsquery('english', %s)) AS score
                FROM chunks
                WHERE tsv @@ plainto_tsquery('english', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (query, query, k * 5),
            )
            pairs = [(r["movie_id"], float(r["score"])) for r in cur.fetchall()]

        return self._collapse(pairs, k)

    # ==============================================================
    # STEP 40 — Method 3: dense vector search
    # ==============================================================
    def dense_search(self, query, k=CANDIDATES):
        """
        Embeds the query, then finds the nearest chunk embeddings.

        Ordering by distance with a LIMIT lets Postgres use the HNSW
        index. Grouping in SQL instead would force a full scan.
        """
        vector = self.embedder.encode([query], normalize_embeddings=True)[0]

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT movie_id, 1 - (embedding <=> %s) AS score
                FROM chunks
                ORDER BY embedding <=> %s
                LIMIT %s
                """,
                (vector, vector, k * 5),
            )
            pairs = [(r["movie_id"], float(r["score"])) for r in cur.fetchall()]

        return self._collapse(pairs, k)

    # ==============================================================
    # STEP 42 — Method 4: Reciprocal Rank Fusion
    # ==============================================================
    @staticmethod
    def fuse(*ranked_lists):
        """
        Merge ranked lists without comparing their scores directly.

        Each list gives a film 1 / (RRF_K + rank) points. A film near the
        top of several lists accumulates the most. BM25 scores and cosine
        similarities are on totally different scales, so merging by
        position rather than value is the correct approach.
        """
        points = defaultdict(float)
        for ranked in ranked_lists:
            for rank, (movie_id, _) in enumerate(ranked):
                points[movie_id] += 1.0 / (RRF_K + rank + 1)
        return sorted(points.items(), key=lambda x: x[1], reverse=True)

    # ==============================================================
    # STEP 44 — Filtering, done in SQL
    # ==============================================================
    def apply_filters(self, ranked, filters):
        """
        Runtime, year, genre and age rating are structured fields,
        so they belong in a WHERE clause, not in the search text.
        """
        if not ranked or not filters:
            return ranked

        ids = [m for m, _ in ranked]
        clauses, params = ["id = ANY(%s)"], [ids]

        if filters.get("max_runtime"):
            clauses.append("runtime > 0 AND runtime <= %s")
            params.append(filters["max_runtime"])

        if filters.get("min_year"):
            clauses.append("year >= %s")
            params.append(filters["min_year"])

        if filters.get("genres"):
            clauses.append("genres && %s")
            params.append(filters["genres"])

        if filters.get("max_age_rating"):
            allowed = {
                "G":     ["G"],
                "PG":    ["G", "PG"],
                "PG-13": ["G", "PG", "PG-13"],
                "R":     ["G", "PG", "PG-13", "R"],
            }
            clauses.append("age_rating = ANY(%s)")
            params.append(allowed.get(filters["max_age_rating"], ["G"]))

        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT id FROM movies WHERE {' AND '.join(clauses)}", params
            )
            keep = {r["id"] for r in cur.fetchall()}

        return [(m, s) for m, s in ranked if m in keep]

    # ==============================================================
    # STEP 45 — Method 5: cross-encoder re-ranking
    # ==============================================================
    def rerank(self, query, candidates, k=FINAL_K):
        """
        Reads the query and each film's text together and scores properly.

        Slow, so it only sees the shortlist. This two-stage pattern —
        fast retrieval then accurate re-ranking — is standard practice.
        """
        if not candidates:
            return []

        ids = [m for m, _ in candidates]
        texts = self._movie_texts(ids)

        pairs = [(query, texts.get(m, "")) for m in ids]
        scores = self.reranker.predict(pairs)

        ranked = sorted(zip(ids, scores), key=lambda x: x[1], reverse=True)
        return [(m, float(s)) for m, s in ranked[:k]]

    def _movie_texts(self, ids, limit=1200):
        """Join a film's chunks into one block for the cross-encoder."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT movie_id, string_agg(content, ' ' ORDER BY id) AS text
                FROM chunks
                WHERE movie_id = ANY(%s)
                GROUP BY movie_id
                """,
                (ids,),
            )
            return {r["movie_id"]: (r["text"] or "")[:limit]
                    for r in cur.fetchall()}

    # ==============================================================
    # STEP 46a — Multi-query expansion
    # ==============================================================
    def multi_query(self, query, variants, k=CANDIDATES):
        """
        Search with the original question plus LLM-written rewrites,
        then fuse the results.

        The Orchestrator generates the variants. This agent never calls
        the LLM itself, so there is one API key and one failure path.
        """
        queries = [query] + [v for v in (variants or []) if v]
        return self.fuse(*[self.dense_search(q, k) for q in queries])[:k]

    # ==============================================================
    # STEP 46b — MMR diversity
    # ==============================================================
    def diversify(self, query, candidates, k=FINAL_K):
        """
        Maximal Marginal Relevance.

        Picks results one at a time, each time choosing the film that is
        relevant but different from what is already chosen. Stops five
        sequels of one franchise filling every slot, and supports the
        fairness goal in the Responsible AI section.
        """
        if len(candidates) <= k:
            return candidates

        ids = [m for m, _ in candidates]
        vectors = self._movie_vectors(ids)
        if not vectors:
            return candidates[:k]

        query_vec = self.embedder.encode([query], normalize_embeddings=True)[0]
        original = dict(candidates)

        chosen, remaining = [], [m for m in ids if m in vectors]

        while remaining and len(chosen) < k:
            best_movie, best_score = None, float("-inf")

            for movie_id in remaining:
                vec = vectors[movie_id]
                relevance = float(query_vec @ vec)
                redundancy = max(
                    (float(vec @ vectors[c]) for c in chosen), default=0.0
                )
                score = MMR_LAMBDA * relevance - (1 - MMR_LAMBDA) * redundancy

                if score > best_score:
                    best_movie, best_score = movie_id, score

            chosen.append(best_movie)
            remaining.remove(best_movie)

        return [(m, original.get(m, 0.0)) for m in chosen]

    def _movie_vectors(self, ids):
        """
        One normalised vector per film, averaged from its chunks.

        Averaged in Python rather than SQL so this works on any
        pgvector version.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT movie_id, embedding FROM chunks WHERE movie_id = ANY(%s)",
                (ids,),
            )
            rows = cur.fetchall()

        grouped = defaultdict(list)
        for row in rows:
            if row["embedding"] is not None:
                grouped[row["movie_id"]].append(np.asarray(row["embedding"]))

        vectors = {}
        for movie_id, vecs in grouped.items():
            mean = np.mean(vecs, axis=0)
            norm = np.linalg.norm(mean)
            vectors[movie_id] = mean / norm if norm > 0 else mean

        return vectors

    # ==============================================================
    # Fetch display records
    # ==============================================================
    def hydrate(self, ranked):
        """Turn (movie_id, score) pairs into full records for the user."""
        if not ranked:
            return []

        ids = [m for m, _ in ranked]
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tmdb_id, title, year, runtime, genres,
                       age_rating, country, director, overview
                FROM movies WHERE id = ANY(%s)
                """,
                (ids,),
            )
            rows = {r["id"]: r for r in cur.fetchall()}

        results = []
        for movie_id, score in ranked:
            row = rows.get(movie_id)
            if not row:
                continue

            record = dict(row)
            record["doc_id"] = f"m{movie_id}"
            record["score"] = round(float(score), 5)
            record["matched_text"] = self._best_chunk(movie_id)
            results.append(record)

        return results

    def _best_chunk(self, movie_id, limit=500):
        """A snippet of the film's text, for the Analysis agent."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT string_agg(content, ' ' ORDER BY id) AS text
                FROM chunks WHERE movie_id = %s AND chunk_type = 'review'
                """,
                (movie_id,),
            )
            row = cur.fetchone()

        if row and row["text"]:
            return row["text"][:limit]

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM chunks WHERE movie_id = %s "
                "AND chunk_type = 'overview' LIMIT 1",
                (movie_id,),
            )
            row = cur.fetchone()

        return (row["content"][:limit] if row else "")

    # ==============================================================
    # One entry point for all six methods
    # ==============================================================
    def search(self, query, filters=None, method="full",
               variants=None, k=FINAL_K):
        """
        method: bm25 | fulltext | dense | hybrid | reranked | full

        The evaluation calls this with each method name in turn.
        """
        if method == "bm25":
            ranked = self.bm25_search(query)

        elif method == "fulltext":
            ranked = self.fulltext_search(query)

        elif method == "dense":
            ranked = self.dense_search(query)

        elif method == "hybrid":
            ranked = self.fuse(
                self.bm25_search(query), self.dense_search(query)
            )

        elif method == "reranked":
            fused = self.fuse(
                self.bm25_search(query), self.dense_search(query)
            )
            fused = self.apply_filters(fused, filters)
            return self.hydrate(self.rerank(query, fused[:CANDIDATES], k))

        elif method == "full":
            sparse = self.bm25_search(query)
            dense = (self.multi_query(query, variants)
                     if variants else self.dense_search(query))

            fused = self.fuse(sparse, dense)
            fused = self.apply_filters(fused, filters)

            shortlist = self.rerank(query, fused[:CANDIDATES], k * 3)
            return self.hydrate(self.diversify(query, shortlist, k))

        else:
            raise ValueError(f"unknown method: {method}")

        ranked = self.apply_filters(ranked, filters)
        return self.hydrate(ranked[:k])

    def close(self):
        self.conn.close()