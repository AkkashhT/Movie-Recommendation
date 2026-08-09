from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List
from pydantic import BaseModel

from app.db.session import get_db
from app.db.redis_client import cache_delete_pattern
from app.core.security import get_current_user
from app.models.user import User, UserPreference
from app.models.movie import Genre, Person, Movie
from app.schemas.auth import OnboardingRequest, UserResponse
from app.schemas.movie import GenreSchema, PersonSchema, MovieCard
import httpx

router = APIRouter(prefix="/users", tags=["users"])


class UpdatePreferencesRequest(BaseModel):
    genre_ids: List[int] = []
    actor_ids: List[int] = []
    director_ids: List[int] = []


@router.post("/onboarding")
async def complete_onboarding(
    req: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    genres = (await db.execute(select(Genre).where(Genre.id.in_(req.genre_ids)))).scalars().all()
    if len(genres) < 3:
        raise HTTPException(400, "At least 3 valid genres required")
    actors = (await db.execute(select(Person).where(Person.id.in_(req.actor_ids)))).scalars().all()
    if len(actors) < 2:
        raise HTTPException(400, "At least 2 valid actors required")
    directors = (await db.execute(select(Person).where(Person.id.in_(req.director_ids)))).scalars().all()
    if len(directors) < 1:
        raise HTTPException(400, "At least 1 valid director required")

    result = await db.execute(select(UserPreference).where(UserPreference.user_id == current_user.id))
    pref = result.scalar_one_or_none()
    if not pref:
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)

    pref.favorite_genre_ids = req.genre_ids
    pref.favorite_actor_ids = req.actor_ids
    pref.favorite_director_ids = req.director_ids
    current_user.onboarding_done = True
    await db.commit()

    try:
        from app.core.config import get_settings
        settings = get_settings()
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.ml_service_url}/embeddings/user/{current_user.id}/init",
                json={"genre_ids": req.genre_ids, "actor_ids": req.actor_ids, "director_ids": req.director_ids}
            )
    except Exception:
        pass

    return {"message": "Onboarding complete", "onboarding_done": True}


@router.put("/preferences")
async def update_preferences(
    req: UpdatePreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == current_user.id))
    pref = result.scalar_one_or_none()
    if not pref:
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)

    pref.favorite_genre_ids = req.genre_ids
    pref.favorite_actor_ids = req.actor_ids
    pref.favorite_director_ids = req.director_ids
    await db.commit()

    await cache_delete_pattern(f"rec:user:{current_user.id}:*")
    return {"message": "Preferences updated"}


@router.get("/preferences")
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == current_user.id))
    pref = result.scalar_one_or_none()
    if not pref:
        return {"genre_ids": [], "actor_ids": [], "director_ids": []}
    return {
        "genre_ids": pref.favorite_genre_ids or [],
        "actor_ids": pref.favorite_actor_ids or [],
        "director_ids": pref.favorite_director_ids or [],
    }


@router.get("/genres", response_model=List[GenreSchema])
async def list_genres(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Genre).order_by(Genre.name))
    return result.scalars().all()


@router.get("/search/persons", response_model=List[PersonSchema])
async def search_persons(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Person).where(Person.name.ilike(f"%{q}%")).order_by(Person.name).limit(limit)
    )
    return result.scalars().all()


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/watchlist")
async def get_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
):
    from app.models.interaction import Watchlist
    from sqlalchemy.orm import selectinload
    offset = (page - 1) * limit
    result = await db.execute(
        select(Watchlist)
        .options(selectinload(Watchlist.movie).selectinload(Movie.genres))
        .where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.added_at.desc())
        .offset(offset).limit(limit)
    )
    items = result.scalars().all()
    return {
        "items": [
            {
                "movie": {
                    "id": w.movie.id, "tmdb_id": w.movie.tmdb_id, "title": w.movie.title,
                    "poster_path": w.movie.poster_path,
                    "vote_average": float(w.movie.vote_average) if w.movie.vote_average else None,
                    "release_date": str(w.movie.release_date) if w.movie.release_date else None,
                    "genres": [{"id": g.id, "name": g.name} for g in w.movie.genres],
                },
                "added_at": w.added_at.isoformat(),
            }
            for w in items
        ],
        "page": page, "limit": limit,
    }
