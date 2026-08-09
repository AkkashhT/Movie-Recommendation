from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from typing import Optional, List

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.movie import Movie, Person, MovieCast, MovieCrew
from app.models.interaction import Watchlist, Rating, UserInteraction, InteractionType
from app.models.user import User
from app.schemas.movie import MovieDetail, MovieCard, SearchResult
import httpx

router = APIRouter(prefix="/movies", tags=["movies"])


async def _enrich_movie_detail(movie: Movie, current_user: Optional[User], db: AsyncSession) -> dict:
    directors = [
        {"id": c.person.id, "tmdb_id": c.person.tmdb_id,
         "name": c.person.name, "profile_path": c.person.profile_path,
         "known_for_dept": c.person.known_for_dept}
        for c in movie.crew if c.job == "Director"
    ]

    cast_out = [
        {
            "person": {"id": c.person.id, "tmdb_id": c.person.tmdb_id,
                       "name": c.person.name, "profile_path": c.person.profile_path,
                       "known_for_dept": c.person.known_for_dept},
            "character": c.character,
            "cast_order": c.cast_order,
            "is_lead": c.is_lead,
        }
        for c in movie.cast[:15]  # top 15 cast members
    ]

    # User-specific fields
    user_rating = None
    in_watchlist = None
    user_liked = None
    if current_user:
        r = await db.execute(
            select(Rating).where(Rating.user_id == current_user.id, Rating.movie_id == movie.id)
        )
        rating_row = r.scalar_one_or_none()
        user_rating = float(rating_row.rating) if rating_row else None

        wl = await db.execute(
            select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.movie_id == movie.id)
        )
        in_watchlist = wl.scalar_one_or_none() is not None

        # Check for explicit LIKE/DISLIKE
        like = await db.execute(
            select(UserInteraction).where(
                UserInteraction.user_id == current_user.id,
                UserInteraction.movie_id == movie.id,
                UserInteraction.type.in_([InteractionType.LIKE, InteractionType.DISLIKE])
            ).order_by(UserInteraction.timestamp.desc()).limit(1)
        )
        last_like = like.scalar_one_or_none()
        if last_like:
            user_liked = last_like.type == InteractionType.LIKE

    return {
        "id": movie.id,
        "tmdb_id": movie.tmdb_id,
        "title": movie.title,
        "original_title": movie.original_title,
        "overview": movie.overview,
        "tagline": movie.tagline,
        "release_date": str(movie.release_date) if movie.release_date else None,
        "runtime": movie.runtime,
        "vote_average": float(movie.vote_average) if movie.vote_average else None,
        "vote_count": movie.vote_count,
        "popularity": float(movie.popularity) if movie.popularity else None,
        "poster_path": movie.poster_path,
        "backdrop_path": movie.backdrop_path,
        "trailer_key": movie.trailer_key,
        "language": movie.language,
        "genres": [{"id": g.id, "name": g.name} for g in movie.genres],
        "cast": cast_out,
        "directors": directors,
        "keywords": [kw.name for kw in movie.keywords[:20]],
        "user_rating": user_rating,
        "in_watchlist": in_watchlist,
        "user_liked": user_liked,
    }


@router.get("/{movie_id}")
async def get_movie(
    movie_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    result = await db.execute(
        select(Movie)
        .options(
            selectinload(Movie.genres),
            selectinload(Movie.cast).selectinload(MovieCast.person),
            selectinload(Movie.crew).selectinload(MovieCrew.person),
            selectinload(Movie.keywords),
        )
        .where(Movie.id == movie_id)
    )
    movie = result.scalar_one_or_none()
    if not movie:
        raise HTTPException(404, "Movie not found")
    return await _enrich_movie_detail(movie, current_user, db)


@router.get("/{movie_id}/similar")
async def similar_movies(
    movie_id: int,
    limit: int = Query(12, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Content-based similarity via pgvector cosine distance."""
    # Get anchor embedding
    anchor = await db.execute(
        text("SELECT embedding FROM movie_embeddings WHERE movie_id = :mid"),
        {"mid": movie_id}
    )
    row = anchor.fetchone()
    if not row:
        # Fallback: return popular movies from same genres
        movie = (await db.execute(select(Movie).where(Movie.id == movie_id))).scalar_one_or_none()
        if not movie:
            raise HTTPException(404, "Movie not found")
        result = await db.execute(
            select(Movie)
            .join(Movie.genres)
            .options(selectinload(Movie.genres))
            .where(Movie.id != movie_id)
            .order_by(Movie.vote_average.desc())
            .limit(limit)
        )
        movies = result.scalars().all()
        return [_movie_card(m) for m in movies]

    # Vector similarity (HNSW index makes this fast)
    similar = await db.execute(
        text("""
            SELECT m.id, m.tmdb_id, m.title, m.poster_path, m.vote_average,
                   m.release_date, 1 - (me.embedding <=> :emb::vector) AS similarity
            FROM movie_embeddings me
            JOIN movies m ON m.id = me.movie_id
            WHERE me.movie_id != :mid
            ORDER BY me.embedding <=> :emb::vector
            LIMIT :limit
        """),
        {"emb": str(row[0]), "mid": movie_id, "limit": limit}
    )
    rows = similar.fetchall()
    # Load genres for each
    movie_ids = [r[0] for r in rows]
    genre_map = await _load_genre_map(movie_ids, db)

    return [
        {
            "id": r[0], "tmdb_id": r[1], "title": r[2],
            "poster_path": r[3],
            "vote_average": float(r[4]) if r[4] else None,
            "release_date": str(r[5]) if r[5] else None,
            "genres": genre_map.get(r[0], []),
            "similarity_score": float(r[6]),
        }
        for r in rows
    ]


@router.get("/{movie_id}/explanation")
async def get_explanation(
    movie_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT explanation_text, content_score, collab_score, neural_score,
                   popularity_score, hybrid_score
            FROM recommendation_explanations
            WHERE user_id = :uid AND movie_id = :mid
        """),
        {"uid": current_user.id, "mid": movie_id}
    )
    row = result.fetchone()
    if not row:
        return {"explanation": "Recommended based on your preferences and popular titles."}
    return {
        "explanation": row[0],
        "scores": {
            "content": float(row[1]) if row[1] else None,
            "collaborative": float(row[2]) if row[2] else None,
            "neural": float(row[3]) if row[3] else None,
            "popularity": float(row[4]) if row[4] else None,
            "hybrid": float(row[5]) if row[5] else None,
        }
    }


def _movie_card(m: Movie) -> dict:
    return {
        "id": m.id,
        "tmdb_id": m.tmdb_id,
        "title": m.title,
        "poster_path": m.poster_path,
        "vote_average": float(m.vote_average) if m.vote_average else None,
        "release_date": str(m.release_date) if m.release_date else None,
        "genres": [{"id": g.id, "name": g.name} for g in m.genres],
    }


async def _load_genre_map(movie_ids: list, db: AsyncSession) -> dict:
    if not movie_ids:
        return {}
    result = await db.execute(
        select(Movie).options(selectinload(Movie.genres)).where(Movie.id.in_(movie_ids))
    )
    movies = result.scalars().all()
    return {
        m.id: [{"id": g.id, "name": g.name} for g in m.genres]
        for m in movies
    }
