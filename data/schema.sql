-- CineMate database schema
-- Postgres 16+ with the pgvector extension
--
-- Setup:
--   createdb cinemate
--   psql cinemate -f schema.sql

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy title matching

-- ---------------------------------------------------------------
-- Movies: one row per film, structured fields for SQL filtering
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS movies (
    id            SERIAL PRIMARY KEY,
    tmdb_id       INTEGER UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    original_title TEXT,
    year          INTEGER,
    release_date  DATE,
    runtime       INTEGER,
    genres        TEXT[],
    age_rating    TEXT,
    country       TEXT,               -- needed for the fairness audit
    language      TEXT,
    popularity    REAL,
    vote_average  REAL,
    vote_count    INTEGER,
    overview      TEXT,
    tagline       TEXT,
    keywords      TEXT[],
    cast_names    TEXT[],
    director      TEXT,
    poster_path   TEXT,
    ingested_at   TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_movies_year    ON movies (year);
CREATE INDEX IF NOT EXISTS idx_movies_runtime ON movies (runtime);
CREATE INDEX IF NOT EXISTS idx_movies_rating  ON movies (age_rating);
CREATE INDEX IF NOT EXISTS idx_movies_genres  ON movies USING gin (genres);
CREATE INDEX IF NOT EXISTS idx_movies_title_trgm
    ON movies USING gin (title gin_trgm_ops);

-- ---------------------------------------------------------------
-- Reviews: raw user reviews, one row each
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id        SERIAL PRIMARY KEY,
    movie_id  INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    author    TEXT,
    content   TEXT NOT NULL,
    rating    REAL,
    source    TEXT DEFAULT 'tmdb'
);

CREATE INDEX IF NOT EXISTS idx_reviews_movie ON reviews (movie_id);

-- ---------------------------------------------------------------
-- Chunks: the units we actually retrieve
-- One movie produces several chunks (overview, keywords, reviews)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id         SERIAL PRIMARY KEY,
    movie_id   INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL,          -- overview | review | metadata
    content    TEXT NOT NULL,
    embedding  VECTOR(384),            -- all-MiniLM-L6-v2 dimension
    tsv        TSVECTOR
);

-- Vector index for dense search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- Full-text index for Postgres keyword search
CREATE INDEX IF NOT EXISTS idx_chunks_tsv
    ON chunks USING gin (tsv);

CREATE INDEX IF NOT EXISTS idx_chunks_movie ON chunks (movie_id);

-- Keep tsv in sync automatically
CREATE OR REPLACE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
BEGIN
    NEW.tsv := to_tsvector('english', COALESCE(NEW.content, ''));
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks;
CREATE TRIGGER trg_chunks_tsv
    BEFORE INSERT OR UPDATE OF content ON chunks
    FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();

-- ---------------------------------------------------------------
-- Users and usage: owned by the Guardian agent
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    age            INTEGER NOT NULL,
    tier           TEXT DEFAULT 'free',
    prefs_encrypted TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS query_log (
    id         SERIAL PRIMARY KEY,
    username   TEXT REFERENCES users(username) ON DELETE CASCADE,
    trace_id   TEXT NOT NULL,
    event      TEXT NOT NULL,
    detail     TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_query_log_user ON query_log (username, created_at);