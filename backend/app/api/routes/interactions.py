from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from typing import Optional
import httpx

from app.db.session import get_db
from app.db.redis_client import cache_delete_pattern
from app.core.security import get_current_user
from app.models.user import User
from app.models.movie import Movie
from app.models.interaction import UserInteraction, InteractionType, INTERACTION_WEIGHTS, Watchlist, Rating
from app.schemas.movie import InteractionRequest
from app.core.config import get_settings

router = APIRouter(prefix="/interactions", tags=["interactions"])
settings = get_settings()


@router.post("")
async def log_interaction(
    req: InteractionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate type
    try:
        itype = InteractionType(req.type)
    except ValueError:
        raise HTTPException(400, f"Invalid interaction type: {req.type}")

    # Validate movie exists
    movie = (await db.execute(select(Movie).where(Movie.id == req.movie_id))).scalar_one_or_none()
    if not movie:
        raise HTTPException(404, "Movie not found")

    # Compute weight
    base_weight = INTERACTION_WEIGHTS.get(itype, 0.0)
    if itype == InteractionType.RATE and req.metadata:
        # Scale rating 1-10 to [-1, 1] for embedding direction
        raw_rating = req.metadata.get("rating", 5)
        base_weight = (raw_rating - 5.5) / 4.5  # center at 5.5, normalize
    final_weight = req.weight if req.weight is not None else base_weight

    interaction = UserInteraction(
        user_id=current_user.id,
        movie_id=req.movie_id,
        type=itype,
        weight=final_weight,
        metadata=req.metadata,
    )
    db.add(interaction)

    # Handle side effects for specific interaction types
    if itype == InteractionType.WISHLIST_ADD:
        existing = (await db.execute(
            select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.movie_id == req.movie_id)
        )).scalar_one_or_none()
        if not existing:
            db.add(Watchlist(user_id=current_user.id, movie_id=req.movie_id))

    elif itype == InteractionType.WISHLIST_REMOVE:
        await db.execute(
            Watchlist.__table__.delete().where(
                Watchlist.user_id == current_user.id,
                Watchlist.movie_id == req.movie_id,
            )
        )

    elif itype == InteractionType.RATE and req.metadata:
        rating_val = req.metadata.get("rating")
        if rating_val is not None:
            existing = (await db.execute(
                select(Rating).where(Rating.user_id == current_user.id, Rating.movie_id == req.movie_id)
            )).scalar_one_or_none()
            if existing:
                existing.rating = rating_val
            else:
                db.add(Rating(user_id=current_user.id, movie_id=req.movie_id, rating=rating_val))

    # Increment interaction count on user
    await db.execute(
        update(User).where(User.id == current_user.id)
        .values(interaction_count=User.interaction_count + 1)
    )

    await db.commit()

    # Async: update user embedding in ML service (non-blocking, live re-ranking)
    if final_weight != 0.0:
        await cache_delete_pattern(f"rec:user:{current_user.id}:*")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{settings.ml_service_url}/embeddings/user/{current_user.id}/update",
                    json={
                        "movie_id": req.movie_id,
                        "weight": float(final_weight),
                        "interaction_type": req.type,
                    }
                )
        except Exception:
            pass  # Non-blocking — will be updated on next batch retrain

    return {"message": "Interaction logged", "weight": float(final_weight)}
