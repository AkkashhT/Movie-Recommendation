from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from typing import Optional
import httpx

from app.db.session import get_db
from app.db.redis_client import cache_set, cache_get
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.models.movie import Movie

router = APIRouter(prefix="/search", tags=["search"])
settings = get_settings()


@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=50),
    page: int = Query(1, ge=1),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Hybrid keyword + semantic search."""
    cache_key = f"search:{q}:{page}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    semantic_results = []
    semantic_used = False

    # Try ML service for semantic search
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.ml_service_url}/search/semantic",
                json={"query": q, "limit": limit}
            )
            if resp.status_code == 200:
                semantic_data = resp.json()
                semantic_results = semantic_data.get("movie_ids", [])
                semantic_used = True
    except Exception:
        pass

    offset = (page - 1) * limit

    if semantic_results:
        # Combine semantic results with full-text, deduplicating
        result = await db.execute(
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(Movie.id.in_(semantic_results))
        )
        movies = result.scalars().all()
        # Maintain semantic ranking order
        id_to_movie = {m.id: m for m in movies}
        ordered = [id_to_movie[mid] for mid in semantic_results if mid in id_to_movie]

        # Also do full-text to catch exact matches not in semantic top-k
        ft_result = await db.execute(
            text("""
                SELECT id FROM movies
                WHERE search_vector @@ plainto_tsquery('english', :q)
                AND id NOT IN :semantic_ids
                ORDER BY ts_rank(search_vector, plainto_tsquery('english', :q)) DESC
                LIMIT 10
            """),
            {"q": q, "semantic_ids": tuple(semantic_results) or (0,)}
        )
        ft_ids = [r[0] for r in ft_result.fetchall()]
        if ft_ids:
            ft_movies = (await db.execute(
                select(Movie).options(selectinload(Movie.genres)).where(Movie.id.in_(ft_ids))
            )).scalars().all()
            # Prepend exact matches to front
            ordered = ft_movies + ordered

        movies_out = ordered[:limit]
    else:
        # Pure full-text fallback
        result = await db.execute(
            text("""
                SELECT m.id FROM movies m
                WHERE m.search_vector @@ plainto_tsquery('english', :q)
                   OR m.title ILIKE :like
                ORDER BY
                    CASE WHEN lower(m.title) = lower(:q) THEN 0 ELSE 1 END,
                    ts_rank(m.search_vector, plainto_tsquery('english', :q)) DESC,
                    m.popularity DESC
                LIMIT :limit OFFSET :offset
            """),
            {"q": q, "like": f"%{q}%", "limit": limit, "offset": offset}
        )
        ids = [r[0] for r in result.fetchall()]
        movies_out_raw = (await db.execute(
            select(Movie).options(selectinload(Movie.genres)).where(Movie.id.in_(ids))
        )).scalars().all()
        id_map = {m.id: m for m in movies_out_raw}
        movies_out = [id_map[i] for i in ids if i in id_map]

    # Log search interaction
    if current_user:
        from app.models.interaction import UserInteraction, InteractionType
        db.add(UserInteraction(
            user_id=current_user.id,
            type=InteractionType.SEARCH_QUERY,
            weight=0.0,
            metadata={"query": q, "results": len(movies_out)},
        ))
        await db.commit()

    response = {
        "movies": [
            {
                "id": m.id, "tmdb_id": m.tmdb_id, "title": m.title,
                "poster_path": m.poster_path,
                "vote_average": float(m.vote_average) if m.vote_average else None,
                "release_date": str(m.release_date) if m.release_date else None,
                "genres": [{"id": g.id, "name": g.name} for g in m.genres],
            }
            for m in movies_out
        ],
        "total": len(movies_out),
        "query": q,
        "semantic_used": semantic_used,
    }

    await cache_set(cache_key, response, ttl=60)
    return response


@router.get("/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Fast autocomplete from titles."""
    result = await db.execute(
        text("""
            SELECT id, title, poster_path, release_date
            FROM movies
            WHERE title ILIKE :pattern
               OR title ILIKE :start
            ORDER BY
                CASE WHEN lower(title) LIKE lower(:start) THEN 0 ELSE 1 END,
                popularity DESC NULLS LAST
            LIMIT :limit
        """),
        {"pattern": f"%{q}%", "start": f"{q}%", "limit": limit}
    )
    rows = result.fetchall()
    return [
        {"id": r[0], "title": r[1], "poster_path": r[2],
         "year": r[3].year if r[3] else None}
        for r in rows
    ]
