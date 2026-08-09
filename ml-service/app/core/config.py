from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class MLSettings(BaseSettings):
    database_url: str = "postgresql+asyncpg://cinemate:cinemate_secret@localhost:5432/cinemate"
    redis_url: str = "redis://localhost:6379"
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    model_dir: str = "/app/models_store"

    # Sentence-transformer model for 384-dim embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Hybrid fusion weights (sum to 1.0); tunable in config without code change
    weight_content: float = 0.35
    weight_collab: float = 0.30
    weight_neural: float = 0.25
    weight_popularity: float = 0.10

    # MMR diversity parameter (0=pure relevance, 1=pure diversity)
    mmr_lambda: float = 0.6

    # Cold-start threshold
    cold_start_threshold: int = 20

    # TMDB ingestion
    movies_to_ingest: int = 4000  # target from Section 8

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_ml_settings() -> MLSettings:
    return MLSettings()
