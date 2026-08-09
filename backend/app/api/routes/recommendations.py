from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from typing import Optional, List
import httpx

from app.db.session import get_db
from app.db.redis_client import cache_set, cache_get
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.user import User, UserPreference
from app.models.movie import Movie

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
settings = get_settings()


async def _call_ml(endpoint: str, payload: dict, timeout: int = 30) -> Optional[dict]:
    """Call ML service with graceful degradation."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{settings.ml_service_url}{endpoint}", json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return None


async def _fallback_popular(db: AsyncSession, genre_ids: list = None, limit: int = 20) -> list:
    """DB-based popularity fallback when ML service is down."""
    q = select(Movie).options(selectinload(Movie.genres)).order_by(
        Movie.vote_average.desc(), Movie.popularity.desc()
    ).limit(limit)
    if genre_ids:
        from app.models.movie import movie_genres_table
        q = q.join(movie_genres_table).where(movie_genres_table.c.genre_id.in_(genre_ids))
    result = await db.execute(q)
    movies = result.scalars().all()
    return [
        {
            "movie": {
                "id": m.id, "tmdb_id": m.tmdb_id, "title": m.title,
                "poster_path": m.poster_path,
                "vote_average": float(m.vote_average) if m.vote_average else None,
                "release_date": str(m.release_date) if m.release_date else None,
                "genres": [{"id": g.id, "name": g.name} for g in m.genres],
            },
            "hybrid_score": float(m.popularity or 0),
            "explanation": "Popular title you might enjoy.",
        }
        for m in movies
    ]


@router.get("/home")
async def get_homepage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All homepage sections."""
    cache_key = f"rec:user:{current_user.id}:home"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )).scalar_one_or_none()

    payload = {
        "user_id": current_user.id,
        "interaction_count": current_user.interaction_count,
        "genre_ids": pref.favorite_genre_ids if pref else [],
        "actor_ids": pref.favorite_actor_ids if pref else [],
        "director_ids": pref.favorite_director_ids if pref else [],
    }

    ml_result = await _call_ml("/recommend/home", payload)

    if ml_result:
        response = ml_result
    else:
        # Graceful degradation fallback
        genre_ids = pref.favorite_genre_ids if pref else None
        popular = await _fallback_popular(db, genre_ids, 20)
        response = {
            "sections": [
                {
                    "section_key": "for_you",
                    "title": "Recommended For You",
                    "items": popular[:12],
                    "anchor_movie": None,
                },
                {
                    "section_key": "trending",
                    "title": "Trending Now",
                    "items": await _fallback_popular(db, None, 12),
                    "anchor_movie": None,
                },
            ],
            "user_interaction_count": current_user.interaction_count,
            "is_cold_start": current_user.interaction_count < settings.cold_start_threshold,
            "_fallback": True,
        }

    await cache_set(cache_key, response, ttl=settings.rec_cache_ttl)
    return response


@router.get("/for-you")
async def for_you(
    limit: int = Query(20, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid personalized feed."""
    cache_key = f"rec:user:{current_user.id}:for_you:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    pref = (await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )).scalar_one_or_none()

    payload = {
        "user_id": current_user.id,
        "interaction_count": current_user.interaction_count,
        "genre_ids": pref.favorite_genre_ids if pref else [],
        "limit": limit,
    }

    result = await _call_ml("/recommend/for-you", payload)
    if not result:
        result = {"items": await _fallback_popular(db, None, limit)}

    await cache_set(cache_key, result, ttl=settings.rec_cache_ttl)
    return result
