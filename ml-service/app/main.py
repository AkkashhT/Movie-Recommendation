"""
Cinemate ML Service
All recommendation algorithms exposed as internal APIs.
Called by the backend; not exposed to the public internet.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional

from app.core.config import get_ml_settings
from app.services.ingestion import run_ingestion
from app.services.content_filter import generate_movie_embeddings
from app.services.collab_filter import get_collab_model, reload_collab_model, CollaborativeFilter
from app.services.neural_cf import get_ncf_model, reload_ncf_model, NCFTrainer
from app.services.embeddings import (
    init_user_embedding_from_preferences,
    update_user_embedding_on_interaction,
    batch_rebuild_user_embeddings,
)
from app.services.hybrid_recommender import hybrid_recommend, get_homepage_sections
from app.services.evaluation import run_evaluation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_ml_settings()

# Training status tracker
_training_status = {"status": "idle", "message": "", "progress": 0}


async def get_conn() -> asyncpg.Connection:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url)


async def get_pool() -> asyncpg.Pool:
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.create_pool(url, min_size=2, max_size=10)


_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    _pool = await get_pool()
    # Load models from disk if available
    get_collab_model()
    get_ncf_model()
    logger.info("ML service ready.")
    yield
    await _pool.close()


app = FastAPI(title="Cinemate ML Service", lifespan=lifespan)


async def _db():
    return await _pool.acquire()


# ─── Health ──────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cinemate-ml"}


# ─── Model Status ────────────────────────────────
@app.get("/models/status")
async def model_status():
    collab = get_collab_model()
    ncf = get_ncf_model()
    return {
        "models": [
            {"name": "collaborative_filter", "trained": collab.is_trained,
             "type": "SVD", "description": "Matrix factorization over user-item ratings"},
            {"name": "neural_cf", "trained": ncf.is_trained,
             "type": "NCF (GMF+MLP)", "description": "Neural collaborative filtering"},
            {"name": "content_embeddings", "trained": True,
             "type": "sentence-transformers", "description": "384-dim semantic embeddings"},
        ]
    }


# ─── Ingestion + Training ─────────────────────────
class TrainRequest(BaseModel):
    target_movies: int = 4000
    ncf_epochs: int = 20


async def _run_pipeline(target_movies: int, ncf_epochs: int):
    global _training_status
    try:
        _training_status = {"status": "running", "message": "Ingesting movies from TMDB...", "progress": 10}
        ingest_result = await run_ingestion(target_movies)

        _training_status["message"] = "Generating movie embeddings..."
        _training_status["progress"] = 35
        async with _pool.acquire() as conn:
            await generate_movie_embeddings(conn)

        _training_status["message"] = "Training collaborative filter (SVD)..."
        _training_status["progress"] = 55
        collab = CollaborativeFilter()
        async with _pool.acquire() as conn:
            await collab.train(conn)
        reload_collab_model()

        _training_status["message"] = "Training neural CF (GMF+MLP)..."
        _training_status["progress"] = 75
        ncf = NCFTrainer()
        async with _pool.acquire() as conn:
            await ncf.train(conn, epochs=ncf_epochs)
        reload_ncf_model()

        _training_status["message"] = "Rebuilding user embeddings..."
        _training_status["progress"] = 90
        async with _pool.acquire() as conn:
            await batch_rebuild_user_embeddings(conn)

        _training_status = {
            "status": "complete",
            "message": "All models trained successfully.",
            "progress": 100,
            "ingest_result": ingest_result,
        }
    except Exception as e:
        _training_status = {"status": "failed", "message": str(e), "progress": 0}
        logger.error(f"Training pipeline failed: {e}", exc_info=True)


@app.post("/training/ingest-and-train")
async def ingest_and_train(req: TrainRequest = TrainRequest(), background_tasks: BackgroundTasks = None):
    if _training_status.get("status") == "running":
        raise HTTPException(409, "Training already in progress")
    background_tasks.add_task(_run_pipeline, req.target_movies, req.ncf_epochs)
    return {"status": "started", "message": "Training pipeline started in background"}


@app.get("/training/status")
async def training_status():
    return _training_status


# ─── Embeddings ──────────────────────────────────
class UserInitRequest(BaseModel):
    genre_ids: List[int]
    actor_ids: List[int]
    director_ids: List[int]


class UserUpdateRequest(BaseModel):
    movie_id: int
    weight: float
    interaction_type: str


@app.post("/embeddings/user/{user_id}/init")
async def init_user_embedding(user_id: int, req: UserInitRequest):
    async with _pool.acquire() as conn:
        await init_user_embedding_from_preferences(
            conn, user_id, req.genre_ids, req.actor_ids, req.director_ids
        )
    return {"status": "ok"}


@app.post("/embeddings/user/{user_id}/update")
async def update_user_embedding(user_id: int, req: UserUpdateRequest):
    """Live embedding update — called on every interaction for instant re-ranking."""
    async with _pool.acquire() as conn:
        await update_user_embedding_on_interaction(conn, user_id, req.movie_id, req.weight)
    return {"status": "ok"}


# ─── Recommendations ─────────────────────────────
class HomeRequest(BaseModel):
    user_id: int
    interaction_count: int
    genre_ids: List[int] = []
    actor_ids: List[int] = []
    director_ids: List[int] = []


class ForYouRequest(BaseModel):
    user_id: int
    interaction_count: int
    genre_ids: List[int] = []
    limit: int = 20


async def _hydrate_movie_ids(conn: asyncpg.Connection, items: list) -> list:
    """Add movie card data to recommendation items."""
    if not items:
        return []
    movie_ids = [item["movie_id"] for item in items]
    rows = await conn.fetch("""
        SELECT m.id, m.tmdb_id, m.title, m.poster_path, m.vote_average,
               m.release_date,
               ARRAY_AGG(DISTINCT g.name) FILTER (WHERE g.name IS NOT NULL) AS genres,
               ARRAY_AGG(DISTINCT g.id) FILTER (WHERE g.id IS NOT NULL) AS genre_ids
        FROM movies m
        LEFT JOIN movie_genres mg ON mg.movie_id = m.id
        LEFT JOIN genres g ON g.id = mg.genre_id
        WHERE m.id = ANY($1)
        GROUP BY m.id
    """, movie_ids)

    movie_map = {r["id"]: dict(r) for r in rows}
    result = []
    for item in items:
        movie = movie_map.get(item["movie_id"])
        if not movie:
            continue
        genres = [{"id": gid, "name": gname}
                  for gid, gname in zip(movie["genre_ids"] or [], movie["genres"] or [])
                  if gid and gname]
        result.append({
            "movie": {
                "id": movie["id"],
                "tmdb_id": movie["tmdb_id"],
                "title": movie["title"],
                "poster_path": movie["poster_path"],
                "vote_average": float(movie["vote_average"]) if movie["vote_average"] else None,
                "release_date": str(movie["release_date"]) if movie["release_date"] else None,
                "genres": genres,
            },
            "hybrid_score": item["hybrid_score"],
            "content_score": item.get("content_score"),
            "collab_score": item.get("collab_score"),
            "neural_score": item.get("neural_score"),
            "popularity_score": item.get("popularity_score"),
            "explanation": item.get("explanation", ""),
        })
    return result


@app.post("/recommend/home")
async def recommend_home(req: HomeRequest):
    async with _pool.acquire() as conn:
        sections_raw = await get_homepage_sections(
            conn, req.user_id, req.interaction_count,
            req.genre_ids, req.actor_ids, req.director_ids,
        )
        # Hydrate each section
        hydrated_sections = []
        for section in sections_raw["sections"]:
            hydrated_items = await _hydrate_movie_ids(conn, section["items"])
            hydrated_sections.append({
                **section,
                "items": hydrated_items,
            })
        return {
            **sections_raw,
            "sections": hydrated_sections,
        }


@app.post("/recommend/for-you")
async def recommend_for_you(req: ForYouRequest):
    async with _pool.acquire() as conn:
        items = await hybrid_recommend(
            conn, req.user_id, req.interaction_count,
            req.genre_ids, limit=req.limit
        )
        hydrated = await _hydrate_movie_ids(conn, items)
    return {"items": hydrated}


# ─── Search ──────────────────────────────────────
class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 20


@app.post("/search/semantic")
async def semantic_search(req: SemanticSearchRequest):
    """Encode query with sentence-transformer, ANN search in pgvector."""
    from app.services.content_filter import get_embedding_model
    model = get_embedding_model()
    query_emb = model.encode([req.query], normalize_embeddings=True)[0].tolist()

    async with _pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT me.movie_id, 1 - (me.embedding <=> $1::vector) AS similarity
            FROM movie_embeddings me
            ORDER BY me.embedding <=> $1::vector
            LIMIT $2
        """, str(query_emb), req.limit)

    return {"movie_ids": [r["movie_id"] for r in rows], "n_results": len(rows)}


# ─── Evaluation ──────────────────────────────────
@app.get("/evaluation/run")
async def run_eval():
    async with _pool.acquire() as conn:
        result = await run_evaluation(conn)
    return result
