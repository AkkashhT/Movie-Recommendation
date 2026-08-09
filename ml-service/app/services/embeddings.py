"""
User Embeddings
---------------
User embedding = weighted rolling average of movie embeddings for positively-interacted movies.
Implements the "YouTube feels like it's reading your mind" live update:
  - On each interaction event (LIKE/VIEW/etc.), update immediately
  - Cold-start: seed from onboarding genre/actor/director picks

Rolling average formula:
  new_emb = normalize(α * old_emb + (1-α) * movie_emb * weight)
  where α = decay factor (0.85 = recent interactions weighted more)
"""
import logging
from typing import List, Optional

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

from app.services.content_filter import get_embedding_model, build_movie_text
from app.core.config import get_ml_settings

logger = logging.getLogger(__name__)
settings = get_ml_settings()

DECAY = 0.85  # exponential moving average decay


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 1e-8 else vec


async def get_user_embedding(conn: asyncpg.Connection, user_id: int) -> Optional[np.ndarray]:
    row = await conn.fetchrow(
        "SELECT embedding FROM user_embeddings WHERE user_id = $1", user_id
    )
    if not row:
        return None
    # Parse pgvector string "[0.1, 0.2, ...]"
    raw = row["embedding"]
    if isinstance(raw, str):
        vec = np.array([float(x) for x in raw.strip("[]").split(",")])
    else:
        vec = np.array(raw)
    return vec


async def set_user_embedding(conn: asyncpg.Connection, user_id: int, embedding: np.ndarray):
    await conn.execute("""
        INSERT INTO user_embeddings (user_id, embedding, model_version)
        VALUES ($1, $2::vector, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET embedding = EXCLUDED.embedding, updated_at = now()
    """, user_id, str(embedding.tolist()), settings.embedding_model)


async def init_user_embedding_from_preferences(
    conn: asyncpg.Connection,
    user_id: int,
    genre_ids: List[int],
    actor_ids: List[int],
    director_ids: List[int],
):
    """
    Cold-start: generate user embedding from onboarding preferences.
    Averages the embeddings of movies matching favorite genres/actors/directors.
    """
    # Find movies that match preferences (genre overlap + cast/crew)
    rows = await conn.fetch("""
        SELECT DISTINCT m.id
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id AND mg.genre_id = ANY($1)
        LEFT JOIN movie_cast mc ON mc.movie_id = m.id AND mc.person_id = ANY($2) AND mc.is_lead
        LEFT JOIN movie_crew cr ON cr.movie_id = m.id AND cr.person_id = ANY($3) AND cr.job = 'Director'
        WHERE (mg.genre_id IS NOT NULL OR mc.person_id IS NOT NULL OR cr.person_id IS NOT NULL)
          AND m.id IN (SELECT movie_id FROM movie_embeddings)
        LIMIT 50
    """, genre_ids, actor_ids, director_ids)

    if not rows:
        logger.warning(f"No preference-matched movies for user {user_id} — using random popular embedding")
        rows = await conn.fetch("""
            SELECT movie_id as id FROM movie_embeddings
            ORDER BY random() LIMIT 20
        """)

    movie_ids = [r["id"] for r in rows]
    emb_rows = await conn.fetch("""
        SELECT embedding FROM movie_embeddings WHERE movie_id = ANY($1)
    """, movie_ids)

    embeddings = []
    for r in emb_rows:
        raw = r["embedding"]
        if isinstance(raw, str):
            vec = np.array([float(x) for x in raw.strip("[]").split(",")])
        else:
            vec = np.array(raw)
        embeddings.append(vec)

    if not embeddings:
        return

    avg_emb = _normalize(np.mean(embeddings, axis=0))
    await set_user_embedding(conn, user_id, avg_emb)
    logger.info(f"Initialized user embedding for user {user_id} from {len(embeddings)} preference movies")


async def update_user_embedding_on_interaction(
    conn: asyncpg.Connection,
    user_id: int,
    movie_id: int,
    weight: float,
):
    """
    Live embedding update triggered immediately on interaction.
    weight > 0: pull toward movie, weight < 0: push away.
    This is the core of the "live re-ranking" feature.
    """
    if abs(weight) < 0.05:
        return  # Ignore very weak signals (e.g., SEARCH_QUERY)

    # Get movie embedding
    movie_row = await conn.fetchrow(
        "SELECT embedding FROM movie_embeddings WHERE movie_id = $1", movie_id
    )
    if not movie_row:
        logger.debug(f"No embedding for movie {movie_id}, skipping update")
        return

    raw = movie_row["embedding"]
    if isinstance(raw, str):
        movie_emb = np.array([float(x) for x in raw.strip("[]").split(",")])
    else:
        movie_emb = np.array(raw)

    # Get current user embedding
    current = await get_user_embedding(conn, user_id)

    if current is None:
        # No existing embedding: initialize from this movie
        new_emb = _normalize(movie_emb * weight if weight > 0 else movie_emb * -weight)
        # If first interaction is negative, we can't do much — init to movie emb anyway
        new_emb = _normalize(movie_emb)
    else:
        # EMA update: blend current toward (or away from) movie embedding
        delta = movie_emb * weight
        new_emb = _normalize(DECAY * current + (1 - DECAY) * delta)

    await set_user_embedding(conn, user_id, new_emb)
    logger.debug(f"Updated embedding for user {user_id} (weight={weight:.2f})")


async def batch_rebuild_user_embeddings(conn: asyncpg.Connection):
    """
    Batch rebuild all user embeddings from interaction history.
    Called during full retraining. Uses weighted sum of interacted movie embeddings.
    """
    user_rows = await conn.fetch("SELECT id FROM users WHERE is_active = true")
    logger.info(f"Rebuilding embeddings for {len(user_rows)} users...")

    for user_row in user_rows:
        user_id = user_row["id"]
        # Fetch all significant interactions
        interactions = await conn.fetch("""
            SELECT ui.movie_id, ui.weight
            FROM user_interactions ui
            JOIN movie_embeddings me ON me.movie_id = ui.movie_id
            WHERE ui.user_id = $1 AND ABS(ui.weight) > 0.1
            ORDER BY ui.timestamp DESC
            LIMIT 200
        """, user_id)

        if not interactions:
            # Check if user has preferences for cold-start
            prefs = await conn.fetchrow("""
                SELECT favorite_genre_ids, favorite_actor_ids, favorite_director_ids
                FROM user_preferences WHERE user_id = $1
            """, user_id)
            if prefs:
                await init_user_embedding_from_preferences(
                    conn, user_id,
                    prefs["favorite_genre_ids"] or [],
                    prefs["favorite_actor_ids"] or [],
                    prefs["favorite_director_ids"] or [],
                )
            continue

        # Weighted average of interacted movie embeddings
        total_weight = 0.0
        weighted_sum = np.zeros(384)

        for row in interactions:
            emb_row = await conn.fetchrow(
                "SELECT embedding FROM movie_embeddings WHERE movie_id = $1", row["movie_id"]
            )
            if not emb_row:
                continue
            raw = emb_row["embedding"]
            if isinstance(raw, str):
                emb = np.array([float(x) for x in raw.strip("[]").split(",")])
            else:
                emb = np.array(raw)
            w = float(row["weight"])
            weighted_sum += emb * w
            total_weight += abs(w)

        if total_weight > 0:
            avg_emb = _normalize(weighted_sum / total_weight)
            await set_user_embedding(conn, user_id, avg_emb)

    logger.info("Batch user embedding rebuild complete.")
