from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func
import httpx

from app.db.session import get_db
from app.core.security import require_admin
from app.core.config import get_settings
from app.models.user import User
from app.models.movie import Movie
from app.models.interaction import UserInteraction, Rating

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


@router.get("/dashboard")
async def dashboard(
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin metrics dashboard."""
    user_count = (await db.execute(select(func.count(User.id)))).scalar()
    movie_count = (await db.execute(select(func.count(Movie.id)))).scalar()
    interaction_count = (await db.execute(select(func.count(UserInteraction.id)))).scalar()
    rating_count = (await db.execute(select(func.count(Rating.id)))).scalar()

    # Embedding coverage
    emb_count = (await db.execute(
        text("SELECT COUNT(*) FROM movie_embeddings")
    )).scalar()

    # ML service health
    ml_health = "unknown"
    ml_models = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ml_service_url}/health")
            if resp.status_code == 200:
                ml_health = "healthy"
                models_resp = await client.get(f"{settings.ml_service_url}/models/status")
                if models_resp.status_code == 200:
                    ml_models = models_resp.json().get("models", [])
    except Exception:
        ml_health = "unreachable"

    # Recent interactions by type
    type_counts = (await db.execute(
        text("""
            SELECT type, COUNT(*) as cnt
            FROM user_interactions
            GROUP BY type
            ORDER BY cnt DESC
        """)
    )).fetchall()

    return {
        "users": {"total": user_count},
        "movies": {"total": movie_count, "with_embeddings": emb_count},
        "interactions": {
            "total": interaction_count,
            "ratings": rating_count,
            "by_type": {r[0]: r[1] for r in type_counts},
        },
        "ml_service": {
            "status": ml_health,
            "models": ml_models,
        },
    }


@router.post("/ml/ingest-and-train")
async def trigger_ingest_and_train(
    admin=Depends(require_admin),
):
    """Trigger ML service ingestion + retraining pipeline."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{settings.ml_service_url}/training/ingest-and-train")
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/ml/training-status")
async def training_status(admin=Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ml_service_url}/training/status")
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/ml/evaluation")
async def run_evaluation(admin=Depends(require_admin)):
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(f"{settings.ml_service_url}/evaluation/run")
            return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}
