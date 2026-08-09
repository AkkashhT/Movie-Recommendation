from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    app_name: str = "Cinemate API"
    environment: str = "development"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://cinemate:cinemate_secret@localhost:5432/cinemate"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # JWT
    secret_key: str = "supersecretkey"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # TMDB
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p"

    # ML Service
    ml_service_url: str = "http://ml-service:8001"
    ml_service_timeout: int = 30

    # Recommendation cache TTL (seconds)
    rec_cache_ttl: int = 300  # 5 minutes

    # Cold-start threshold — interactions below this blend toward content/popularity
    cold_start_threshold: int = 20

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
