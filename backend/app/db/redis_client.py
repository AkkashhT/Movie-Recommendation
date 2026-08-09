import redis.asyncio as aioredis
from app.core.config import get_settings
import json
from typing import Optional, Any

settings = get_settings()
_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    r = await get_redis()
    await r.setex(key, ttl, json.dumps(value))


async def cache_get(key: str) -> Optional[Any]:
    r = await get_redis()
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def cache_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    keys = await r.keys(pattern)
    if keys:
        await r.delete(*keys)
