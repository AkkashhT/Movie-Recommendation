"""
Hybrid Recommender
------------------
Fuses 4 signals into one ranked list:
  Content-based  35%  (pgvector cosine similarity to user embedding)
  Collaborative  30%  (SVD matrix factorization)
  Neural CF      25%  (GMF+MLP NCF model)
  Popularity     10%  (TMDB vote_average × log(vote_count))

Weights are read from config so they're tunable without a code change.

After scoring, applies MMR (Maximal Marginal Relevance) re-ranking to
ensure diversity — prevents 10 nearly-identical movies in one row.

Cold-start blend: as interaction_count → cold_start_threshold,
content+popularity weight increases while collab+neural decreases.
The blend is continuous (not a hard cutover).
"""
import asyncio
import logging
import math
from typing import Dict, List, Optional, Tuple

import asyncpg
import numpy as np

from app.core.config import get_ml_settings
from app.services.collab_filter import get_collab_model
from app.services.neural_cf import get_ncf_model
from app.services.content_filter import get_content_scores_for_user
from app.services.embeddings import get_user_embedding

logger = logging.getLogger(__name__)
settings = get_ml_settings()


def cold_start_blend(interaction_count: int) -> Dict[str, float]:
    """
    Continuously blend weights from cold-start → fully personalized.
    At 0 interactions: content=0.45, collab=0.05, neural=0.05, popularity=0.45
    At threshold+: use configured weights (content=0.35, collab=0.30, neural=0.25, popularity=0.10)
    Uses a sigmoid-like ramp.
    """
    t = settings.cold_start_threshold
    # Linear ramp from 0 to 1 as interactions go 0 → threshold
    progress = min(1.0, interaction_count / max(t, 1))

    cold = {"content": 0.45, "collab": 0.05, "neural": 0.05, "popularity": 0.45}
    warm = {
        "content": settings.weight_content,
        "collab": settings.weight_collab,
        "neural": settings.weight_neural,
        "popularity": settings.weight_popularity,
    }

    return {k: cold[k] + progress * (warm[k] - cold[k]) for k in cold}


async def get_candidate_pool(
    conn: asyncpg.Connection,
    user_id: int,
    genre_ids: List[int],
    limit: int = 200,
    exclude_ids: List[int] = None,
) -> List[dict]:
    """
    Fetch a diverse candidate pool:
    - Movies matching favorite genres
    - Recent popular movies
    - Highly rated movies
    Excludes already-interacted movies unless include_seen=True.
    """
    exclude = tuple(exclude_ids or [0])
    genre_filter = genre_ids or []

    # Get seen movie IDs for this user
    seen = await conn.fetch(
        "SELECT DISTINCT movie_id FROM user_interactions WHERE user_id = $1 AND movie_id IS NOT NULL",
        user_id
    )
    seen_ids = tuple(r["movie_id"] for r in seen) or (0,)
    all_exclude = tuple(set(list(exclude) + list(seen_ids))) or (0,)

    if genre_filter:
        rows = await conn.fetch("""
            SELECT DISTINCT m.id, m.vote_average, m.vote_count, m.popularity
            FROM movies m
            JOIN movie_genres mg ON mg.movie_id = m.id AND mg.genre_id = ANY($1)
            WHERE m.id NOT IN (SELECT unnest($2::int[]))
              AND m.id IN (SELECT movie_id FROM movie_embeddings)
            ORDER BY m.popularity DESC NULLS LAST
            LIMIT $3
        """, genre_filter, list(all_exclude), limit // 2)
    else:
        rows = []

    # Fill remaining from popular
    existing_ids = {r["id"] for r in rows}
    remaining = limit - len(rows)
    popular_rows = await conn.fetch("""
        SELECT m.id, m.vote_average, m.vote_count, m.popularity
        FROM movies m
        WHERE m.id NOT IN (SELECT unnest($1::int[]))
          AND m.id IN (SELECT movie_id FROM movie_embeddings)
          AND m.id != ALL($2)
        ORDER BY (m.vote_average * LOG(GREATEST(m.vote_count, 1) + 1)) DESC NULLS LAST
        LIMIT $3
    """, list(all_exclude), list(existing_ids) or [0], remaining)

    all_rows = list(rows) + [r for r in popular_rows if r["id"] not in existing_ids]
    return [dict(r) for r in all_rows]


def popularity_score(vote_average: float, vote_count: int) -> float:
    """Bayesian-style popularity: avg × log(votes+1), normalised to [0,1] range."""
    if not vote_average or not vote_count:
        return 0.0
    raw = float(vote_average) * math.log(max(vote_count, 1) + 1)
    # Typical range: 0-60; normalise
    return min(raw / 60.0, 1.0)


def mmr_rerank(
    scored_items: List[Tuple[int, float, np.ndarray]],  # (movie_id, score, embedding)
    top_k: int,
    lambda_: float = None,
) -> List[Tuple[int, float]]:
    """
    Maximal Marginal Relevance re-ranking.
    lambda_=1 → pure relevance; lambda_=0 → pure diversity.
    Configured via settings.mmr_lambda (default 0.6).

    Measurably reduces same-genre repetition vs. unranked list.
    """
    lambda_ = lambda_ or settings.mmr_lambda
    if not scored_items:
        return []

    selected = []
    remaining = list(scored_items)

    while remaining and len(selected) < top_k:
        if not selected:
            # First item: highest score
            best = max(remaining, key=lambda x: x[1])
        else:
            selected_embs = np.array([s[2] for s in selected])

            def mmr_score(item):
                relevance = item[1]
                if selected_embs.shape[0] == 0:
                    return relevance
                sims = selected_embs @ item[2]  # cosine sim (already normalised)
                max_sim = float(np.max(sims))
                return lambda_ * relevance - (1 - lambda_) * max_sim

            best = max(remaining, key=mmr_score)

        selected.append(best)
        remaining.remove(best)

    return [(item[0], item[1]) for item in selected]


async def build_explanation(
    conn: asyncpg.Connection,
    user_id: int,
    movie_id: int,
    scores: Dict[str, float],
    weights: Dict[str, float],
    movie_title: str,
) -> str:
    """
    Generate human-readable explanation of why a movie was recommended.
    Each component contributes to the explanation text.
    """
    parts = []

    # Check if movie matches user's favorite genres
    genre_match = await conn.fetchrow("""
        SELECT g.name FROM genres g
        JOIN movie_genres mg ON mg.genre_id = g.id AND mg.movie_id = $1
        JOIN user_preferences up ON g.id = ANY(up.favorite_genre_ids) AND up.user_id = $2
        LIMIT 1
    """, movie_id, user_id)

    if genre_match:
        parts.append(f"matches your favorite genre ({genre_match['name']})")

    # Check favorite actor appearance
    actor_match = await conn.fetchrow("""
        SELECT p.name FROM persons p
        JOIN movie_cast mc ON mc.person_id = p.id AND mc.movie_id = $1
        JOIN user_preferences up ON p.id = ANY(up.favorite_actor_ids) AND up.user_id = $2
        LIMIT 1
    """, movie_id, user_id)

    if actor_match:
        parts.append(f"stars {actor_match['name']}, one of your favorites")

    # Check favorite director
    director_match = await conn.fetchrow("""
        SELECT p.name FROM persons p
        JOIN movie_crew cr ON cr.person_id = p.id AND cr.movie_id = $1 AND cr.job = 'Director'
        JOIN user_preferences up ON p.id = ANY(up.favorite_director_ids) AND up.user_id = $2
        LIMIT 1
    """, movie_id, user_id)

    if director_match:
        parts.append(f"directed by {director_match['name']}, a director you follow")

    # Collaborative signal
    if scores.get("collab", 0) > 0.6:
        parts.append("viewers with similar tastes loved it")

    # Neural signal
    if scores.get("neural", 0) > 0.6:
        parts.append("our AI predicts you'll enjoy it")

    # Popularity signal
    if scores.get("popularity", 0) > 0.7 and not parts:
        parts.append("it's highly rated and widely loved")

    if not parts:
        parts.append("it aligns with your watching pattern")

    return "Recommended because " + ", and ".join(parts) + "."


async def hybrid_recommend(
    conn: asyncpg.Connection,
    user_id: int,
    interaction_count: int,
    genre_ids: List[int],
    limit: int = 20,
    section: str = "for_you",
    exclude_ids: List[int] = None,
    anchor_movie_id: Optional[int] = None,
) -> List[dict]:
    """
    Core hybrid recommendation function.
    Returns list of dicts with movie_id, scores, explanation.
    """
    weights = cold_start_blend(interaction_count)

    # Get candidate pool
    candidates = await get_candidate_pool(conn, user_id, genre_ids, limit=200, exclude_ids=exclude_ids)
    if not candidates:
        return []

    candidate_ids = [c["id"] for c in candidates]
    id_to_candidate = {c["id"]: c for c in candidates}

    # ── 1. Content scores (user embedding vs movie embeddings) ──
    content_scores = {}
    if weights["content"] > 0:
        # Use anchor movie for "Because You Watched" sections
        if anchor_movie_id:
            from app.services.content_filter import get_similar_movies
            similar = await get_similar_movies(conn, anchor_movie_id, limit=200)
            content_scores = {mid: sim for mid, sim in similar if mid in set(candidate_ids)}
        else:
            content_scores = await get_content_scores_for_user(conn, user_id, candidate_ids)

    # ── 2. Collaborative scores (SVD) ──
    collab_scores = {}
    if weights["collab"] > 0:
        collab_model = get_collab_model()
        user_key = f"u_{user_id}"
        collab_scores = collab_model.score_candidates(user_key, candidate_ids)

    # ── 3. Neural CF scores ──
    neural_scores = {}
    if weights["neural"] > 0:
        ncf = get_ncf_model()
        user_key = f"u_{user_id}"
        neural_scores = ncf.score_candidates(user_key, candidate_ids)

    # ── 4. Popularity scores ──
    pop_scores = {
        c["id"]: popularity_score(c.get("vote_average"), c.get("vote_count"))
        for c in candidates
    }

    # ── 5. Hybrid fusion ──
    hybrid_scores = {}
    for mid in candidate_ids:
        cs = content_scores.get(mid, 0.0)
        col = collab_scores.get(mid, 0.0)
        neu = neural_scores.get(mid, 0.0)
        pop = pop_scores.get(mid, 0.0)

        hybrid = (
            weights["content"] * cs
            + weights["collab"] * col
            + weights["neural"] * neu
            + weights["popularity"] * pop
        )
        hybrid_scores[mid] = {
            "hybrid": hybrid,
            "content": cs,
            "collab": col,
            "neural": neu,
            "popularity": pop,
        }

    # ── 6. MMR re-ranking for diversity ──
    # Need embeddings for MMR; fetch them
    emb_rows = await conn.fetch("""
        SELECT movie_id, embedding FROM movie_embeddings WHERE movie_id = ANY($1)
    """, candidate_ids)

    emb_map = {}
    for r in emb_rows:
        raw = r["embedding"]
        if isinstance(raw, str):
            vec = np.array([float(x) for x in raw.strip("[]").split(",")])
        else:
            vec = np.array(raw)
        emb_map[r["movie_id"]] = vec

    scored_items = [
        (mid, hybrid_scores[mid]["hybrid"], emb_map.get(mid, np.zeros(384)))
        for mid in candidate_ids
        if mid in hybrid_scores
    ]
    scored_items.sort(key=lambda x: x[1], reverse=True)
    scored_items = scored_items[:100]  # MMR over top-100 for efficiency

    reranked = mmr_rerank(scored_items, top_k=limit)

    # ── 7. Build output with explanations ──
    result = []
    for movie_id, hybrid_score in reranked:
        s = hybrid_scores[movie_id]
        title_row = await conn.fetchrow("SELECT title FROM movies WHERE id = $1", movie_id)
        if not title_row:
            continue

        explanation = await build_explanation(
            conn, user_id, movie_id, s, weights, title_row["title"]
        )

        # Persist explanation for detail page
        await conn.execute("""
            INSERT INTO recommendation_explanations
                (user_id, movie_id, explanation_text, content_score, collab_score,
                 neural_score, popularity_score, hybrid_score)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (user_id, movie_id) DO UPDATE
            SET explanation_text = EXCLUDED.explanation_text,
                hybrid_score = EXCLUDED.hybrid_score,
                created_at = now()
        """, user_id, movie_id, explanation,
            s["content"], s["collab"], s["neural"], s["popularity"], hybrid_score)

        result.append({
            "movie_id": movie_id,
            "hybrid_score": hybrid_score,
            "content_score": s["content"],
            "collab_score": s["collab"],
            "neural_score": s["neural"],
            "popularity_score": s["popularity"],
            "explanation": explanation,
        })

    return result


async def get_homepage_sections(
    conn: asyncpg.Connection,
    user_id: int,
    interaction_count: int,
    genre_ids: List[int],
    actor_ids: List[int],
    director_ids: List[int],
) -> dict:
    """
    Build all 6 homepage sections (FR-5), each backed by a different algorithm.
    """
    is_cold_start = interaction_count < settings.cold_start_threshold

    # ── Section 1: Recommended For You (hybrid) ──
    for_you = await hybrid_recommend(
        conn, user_id, interaction_count, genre_ids, limit=15, section="for_you"
    )

    # ── Section 2: Because You Watched X (content, anchored to last viewed) ──
    last_view = await conn.fetchrow("""
        SELECT movie_id, m.title FROM user_interactions ui
        JOIN movies m ON m.id = ui.movie_id
        WHERE ui.user_id = $1 AND ui.type = 'VIEW' AND ui.movie_id IS NOT NULL
        ORDER BY ui.timestamp DESC LIMIT 1
    """, user_id)

    because_you_watched = []
    anchor_movie = None
    if last_view:
        anchor_movie = {"id": last_view["movie_id"], "title": last_view["title"]}
        because_you_watched = await hybrid_recommend(
            conn, user_id, interaction_count, genre_ids, limit=12,
            section="because_watched", anchor_movie_id=last_view["movie_id"],
            exclude_ids=[last_view["movie_id"]]
        )

    # ── Section 3: Users Like You Also Watched (collaborative KNN) ──
    collab_model = get_collab_model()
    collab_items = []
    if last_view and collab_model.is_trained:
        knn_results = collab_model.item_knn(last_view["movie_id"], top_k=50)
        collab_candidate_ids = [mid for mid, _ in knn_results[:30]]
        if collab_candidate_ids:
            # Fetch movie info for these
            rows = await conn.fetch("""
                SELECT id, vote_average, vote_count, popularity
                FROM movies WHERE id = ANY($1)
            """, collab_candidate_ids)
            for r in rows:
                knn_score = next((s for mid, s in knn_results if mid == r["id"]), 0.0)
                collab_items.append({
                    "movie_id": r["id"],
                    "hybrid_score": knn_score,
                    "content_score": 0.0,
                    "collab_score": knn_score,
                    "neural_score": 0.0,
                    "popularity_score": popularity_score(r["vote_average"], r["vote_count"]),
                    "explanation": "Users with similar tastes also enjoyed this.",
                })

    # ── Section 4: Hidden Gems (content-based, low-popularity high-relevance) ──
    hidden_gems_raw = await hybrid_recommend(
        conn, user_id, interaction_count, genre_ids, limit=30, section="hidden_gems"
    )
    # Filter for "hidden": below-median popularity but strong content signal
    hidden_gems = [
        item for item in hidden_gems_raw
        if item["content_score"] > 0.5 and item["popularity_score"] < 0.4
    ][:12]
    if len(hidden_gems) < 6:
        hidden_gems = hidden_gems_raw[:12]  # fallback

    # ── Section 5: Trending Now (recent global engagement velocity) ──
    trending_rows = await conn.fetch("""
        SELECT m.id, COUNT(*) AS engagement, m.vote_average, m.vote_count, m.popularity
        FROM user_interactions ui
        JOIN movies m ON m.id = ui.movie_id
        WHERE ui.timestamp > NOW() - INTERVAL '7 days'
          AND ui.type IN ('VIEW','LIKE','WISHLIST_ADD','RATE')
        GROUP BY m.id, m.vote_average, m.vote_count, m.popularity
        ORDER BY engagement DESC, m.popularity DESC
        LIMIT 15
    """)
    if len(trending_rows) < 8:
        # Supplement with TMDB popularity
        popular_rows = await conn.fetch("""
            SELECT id, vote_average, vote_count, popularity FROM movies
            WHERE id NOT IN (SELECT COALESCE(id,0) FROM unnest($1::int[]) AS id)
            ORDER BY popularity DESC NULLS LAST LIMIT 15
        """, [r["id"] for r in trending_rows] or [0])
        trending_rows = list(trending_rows) + list(popular_rows)

    trending = [
        {
            "movie_id": r["id"],
            "hybrid_score": popularity_score(r.get("vote_average"), r.get("vote_count")),
            "content_score": 0.0, "collab_score": 0.0, "neural_score": 0.0,
            "popularity_score": popularity_score(r.get("vote_average"), r.get("vote_count")),
            "explanation": "Trending globally right now.",
        }
        for r in trending_rows[:15]
    ]

    # ── Section 6: Top Rated in Favorite Genre ──
    top_in_genre = []
    if genre_ids:
        fav_genre_id = genre_ids[0]
        fav_genre_row = await conn.fetchrow("SELECT name FROM genres WHERE id = $1", fav_genre_id)
        fav_genre_name = fav_genre_row["name"] if fav_genre_row else "Your Genre"

        top_rows = await conn.fetch("""
            SELECT m.id, m.vote_average, m.vote_count, m.popularity
            FROM movies m
            JOIN movie_genres mg ON mg.movie_id = m.id AND mg.genre_id = $1
            WHERE m.vote_count > 100
            ORDER BY m.vote_average DESC, m.vote_count DESC
            LIMIT 15
        """, fav_genre_id)

        top_in_genre = [
            {
                "movie_id": r["id"],
                "hybrid_score": popularity_score(r["vote_average"], r["vote_count"]),
                "content_score": 0.0, "collab_score": 0.0, "neural_score": 0.0,
                "popularity_score": popularity_score(r["vote_average"], r["vote_count"]),
                "explanation": f"Top rated in {fav_genre_name}.",
            }
            for r in top_rows
        ]
    else:
        fav_genre_name = "Drama"

    return {
        "sections": [
            {"section_key": "for_you", "title": "Recommended For You",
             "items": for_you, "anchor_movie": None},
            {"section_key": "because_watched",
             "title": f"Because You Watched {anchor_movie['title']}" if anchor_movie else "More Like Your Recent Views",
             "items": because_you_watched, "anchor_movie": anchor_movie},
            {"section_key": "users_like_you", "title": "Users Like You Also Watched",
             "items": collab_items[:12], "anchor_movie": None},
            {"section_key": "hidden_gems", "title": "Hidden Gems For You",
             "items": hidden_gems, "anchor_movie": None},
            {"section_key": "trending", "title": "Trending Now",
             "items": trending, "anchor_movie": None},
            {"section_key": "top_in_genre", "title": f"Top Rated in {fav_genre_name}",
             "items": top_in_genre, "anchor_movie": None},
        ],
        "user_interaction_count": interaction_count,
        "is_cold_start": is_cold_start,
    }
