-- Cinemate Database Schema
-- PostgreSQL 16 + pgvector extension
-- All tables from Section 4 of the spec

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for fuzzy text search
CREATE EXTENSION IF NOT EXISTS unaccent;  -- for accent-insensitive search

-- ─────────────────────────────────────────────
-- GENRES  (canonical TMDB taxonomy, 19 genres)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS genres (
    id          INTEGER PRIMARY KEY,  -- TMDB genre id
    name        TEXT NOT NULL UNIQUE
);

-- ─────────────────────────────────────────────
-- PERSONS  (actors + directors from TMDB)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS persons (
    id              SERIAL PRIMARY KEY,
    tmdb_id         INTEGER UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    profile_path    TEXT,
    biography       TEXT,
    known_for_dept  TEXT   -- "Acting", "Directing", etc.
);
CREATE INDEX IF NOT EXISTS idx_persons_name_trgm ON persons USING gin(name gin_trgm_ops);

-- ─────────────────────────────────────────────
-- MOVIES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movies (
    id              SERIAL PRIMARY KEY,
    tmdb_id         INTEGER UNIQUE NOT NULL,
    movielens_id    INTEGER,          -- from links.csv join
    title           TEXT NOT NULL,
    original_title  TEXT,
    overview        TEXT,
    tagline         TEXT,
    release_date    DATE,
    runtime         INTEGER,          -- minutes
    budget          BIGINT,
    revenue         BIGINT,
    vote_average    NUMERIC(4,2),
    vote_count      INTEGER,
    popularity      NUMERIC(10,4),
    poster_path     TEXT,
    backdrop_path   TEXT,
    trailer_key     TEXT,             -- YouTube key from TMDB videos
    language        TEXT,
    status          TEXT,
    adult           BOOLEAN DEFAULT FALSE,
    -- full-text search vector (computed from title+overview+keywords)
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(original_title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(overview, '')), 'B')
    ) STORED,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_movies_tmdb_id ON movies(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_movies_movielens_id ON movies(movielens_id);
CREATE INDEX IF NOT EXISTS idx_movies_search ON movies USING gin(search_vector);
CREATE INDEX IF NOT EXISTS idx_movies_popularity ON movies(popularity DESC);
CREATE INDEX IF NOT EXISTS idx_movies_vote_avg ON movies(vote_average DESC);
CREATE INDEX IF NOT EXISTS idx_movies_release_date ON movies(release_date DESC);

-- ─────────────────────────────────────────────
-- MOVIE_GENRES  (M:N)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movie_genres (
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    genre_id    INTEGER REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);
CREATE INDEX IF NOT EXISTS idx_movie_genres_genre ON movie_genres(genre_id);

-- ─────────────────────────────────────────────
-- KEYWORDS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS keywords (
    id      INTEGER PRIMARY KEY,  -- TMDB keyword id
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS movie_keywords (
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    keyword_id  INTEGER REFERENCES keywords(id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, keyword_id)
);

-- ─────────────────────────────────────────────
-- MOVIE_CAST  (Section 8: cast_order < 3 = is_lead)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movie_cast (
    id          SERIAL PRIMARY KEY,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    person_id   INTEGER REFERENCES persons(id) ON DELETE CASCADE,
    character   TEXT,
    cast_order  INTEGER NOT NULL,   -- TMDB billing order (0-indexed)
    is_lead     BOOLEAN NOT NULL    -- TRUE if cast_order < 3
);
CREATE INDEX IF NOT EXISTS idx_movie_cast_movie ON movie_cast(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_cast_person ON movie_cast(person_id);

-- ─────────────────────────────────────────────
-- MOVIE_CREW
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movie_crew (
    id          SERIAL PRIMARY KEY,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    person_id   INTEGER REFERENCES persons(id) ON DELETE CASCADE,
    job         TEXT NOT NULL,      -- "Director", "Producer", etc.
    department  TEXT
);
CREATE INDEX IF NOT EXISTS idx_movie_crew_movie ON movie_crew(movie_id);
CREATE INDEX IF NOT EXISTS idx_movie_crew_person ON movie_crew(person_id);
CREATE INDEX IF NOT EXISTS idx_movie_crew_directors ON movie_crew(movie_id) WHERE job = 'Director';

-- ─────────────────────────────────────────────
-- MOVIE_EMBEDDINGS  (384-dim sentence-transformer)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movie_embeddings (
    movie_id        INTEGER PRIMARY KEY REFERENCES movies(id) ON DELETE CASCADE,
    embedding       vector(384) NOT NULL,
    model_version   TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_at      TIMESTAMPTZ DEFAULT now()
);
-- HNSW index for sub-100ms ANN search
CREATE INDEX IF NOT EXISTS idx_movie_embeddings_hnsw
    ON movie_embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  SERIAL PRIMARY KEY,
    email               TEXT UNIQUE NOT NULL,
    username            TEXT UNIQUE NOT NULL,
    hashed_password     TEXT NOT NULL,
    full_name           TEXT,
    avatar_url          TEXT,
    role                TEXT NOT NULL DEFAULT 'USER',  -- USER | ADMIN
    is_active           BOOLEAN DEFAULT TRUE,
    onboarding_done     BOOLEAN DEFAULT FALSE,
    interaction_count   INTEGER DEFAULT 0,   -- cached count for cold-start blend calc
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ─────────────────────────────────────────────
-- USER_PREFERENCES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id             INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    favorite_genre_ids  INTEGER[] NOT NULL DEFAULT '{}',
    favorite_actor_ids  INTEGER[] NOT NULL DEFAULT '{}',   -- person.id refs
    favorite_director_ids INTEGER[] NOT NULL DEFAULT '{}',
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- USER_EMBEDDINGS  (384-dim rolling average)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_embeddings (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    embedding       vector(384) NOT NULL,
    model_version   TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- RATINGS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ratings (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    rating      NUMERIC(3,1) NOT NULL CHECK (rating >= 0.5 AND rating <= 10),
    source      TEXT DEFAULT 'user',   -- 'user' | 'movielens'
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, movie_id)
);
CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ratings_movie ON ratings(movie_id);

-- ─────────────────────────────────────────────
-- USER_INTERACTIONS  (event stream)
-- ─────────────────────────────────────────────
CREATE TYPE interaction_type AS ENUM (
    'CLICK', 'VIEW', 'WATCH_TIME', 'RATE',
    'LIKE', 'DISLIKE', 'WISHLIST_ADD', 'WISHLIST_REMOVE', 'SEARCH_QUERY'
);

CREATE TABLE IF NOT EXISTS user_interactions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE SET NULL,
    type        interaction_type NOT NULL,
    weight      NUMERIC(4,2),   -- positive: LIKE/CLICK; negative: DISLIKE; 0-1 for WATCH_TIME
    metadata    JSONB,          -- e.g. {"seconds": 120} for WATCH_TIME, {"query": "..."} for SEARCH
    timestamp   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_interactions_user_time ON user_interactions(user_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_movie ON user_interactions(movie_id);
CREATE INDEX IF NOT EXISTS idx_interactions_type ON user_interactions(type);

-- ─────────────────────────────────────────────
-- WATCHLIST / FAVORITES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    added_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

CREATE TABLE IF NOT EXISTS favorites (
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    movie_id    INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    added_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, movie_id)
);

-- ─────────────────────────────────────────────
-- SEARCH_HISTORY
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS search_history (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    query       TEXT NOT NULL,
    result_count INTEGER,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id, created_at DESC);

-- ─────────────────────────────────────────────
-- RECOMMENDATION_CACHE
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendation_cache (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    section         TEXT NOT NULL,   -- 'for_you', 'because_you_watched', etc.
    movie_ids       INTEGER[] NOT NULL,
    generated_at    TIMESTAMPTZ DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    UNIQUE(user_id, section)
);

-- ─────────────────────────────────────────────
-- RECOMMENDATION_EXPLANATIONS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS recommendation_explanations (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER REFERENCES users(id) ON DELETE CASCADE,
    movie_id            INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    explanation_text    TEXT NOT NULL,
    content_score       NUMERIC(6,4),
    collab_score        NUMERIC(6,4),
    neural_score        NUMERIC(6,4),
    popularity_score    NUMERIC(6,4),
    hybrid_score        NUMERIC(6,4),
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, movie_id)
);

-- ─────────────────────────────────────────────
-- ML_MODELS  (registry / versioning)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ml_models (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,        -- 'svd', 'ncf', 'content_embeddings'
    version         TEXT NOT NULL,
    file_path       TEXT,
    metrics         JSONB,                -- {"rmse": 0.87, "precision_at_10": 0.23}
    status          TEXT DEFAULT 'pending',  -- pending | training | ready | failed
    trained_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- REFRESH_TOKENS  (JWT rotation)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);

-- ─────────────────────────────────────────────
-- MOVIELENS_RATINGS  (pre-training data, separate table)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS movielens_ratings (
    id              BIGSERIAL PRIMARY KEY,
    movielens_user  INTEGER NOT NULL,    -- MovieLens userId (not our users table)
    movie_id        INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    rating          NUMERIC(3,1) NOT NULL,
    ml_timestamp    BIGINT               -- original unix timestamp from ML dataset
);
CREATE INDEX IF NOT EXISTS idx_ml_ratings_movie ON movielens_ratings(movie_id);
CREATE INDEX IF NOT EXISTS idx_ml_ratings_user ON movielens_ratings(movielens_user);
