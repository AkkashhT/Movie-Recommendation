import asyncio
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Optional

import asyncpg
import httpx
import pandas as pd

from app.core.config import get_ml_settings

logger = logging.getLogger(__name__)
settings = get_ml_settings()

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"


async def get_db_conn():
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url)


async def fetch_tmdb_page(client, endpoint, page):
    resp = await client.get(
        f"{settings.tmdb_base_url}{endpoint}",
        params={"page": page, "language": "en-US"},
        headers={"Authorization": f"Bearer {settings.tmdb_api_key}"},
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_movie_details(client, tmdb_id):
    for attempt in range(3):
        try:
            resp = await client.get(
                f"{settings.tmdb_base_url}/movie/{tmdb_id}",
                params={"append_to_response": "credits,keywords,videos"},
                headers={"Authorization": f"Bearer {settings.tmdb_api_key}"},
            )
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 10))
                logger.warning(f"Rate limited, waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Attempt {attempt+1} failed for {tmdb_id}: {e}")
            await asyncio.sleep(2 * (attempt + 1))
    return None


def extract_trailer_key(videos):
    results = videos.get("results", [])
    for v in results:
        if v.get("site") == "YouTube" and v.get("type") == "Trailer" and v.get("official"):
            return v["key"]
    for v in results:
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            return v["key"]
    return None


async def upsert_movie(conn, detail, movielens_id_map):
    tmdb_id = detail["id"]
    ml_id = movielens_id_map.get(tmdb_id)

    trailer_key = None
    if "videos" in detail:
        trailer_key = extract_trailer_key(detail["videos"])

    movie_id = await conn.fetchval("""
        INSERT INTO movies (
            tmdb_id, movielens_id, title, original_title, overview, tagline,
            release_date, runtime, budget, revenue, vote_average, vote_count,
            popularity, poster_path, backdrop_path, trailer_key, language, status, adult
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
        ON CONFLICT (tmdb_id) DO UPDATE SET
            movielens_id = EXCLUDED.movielens_id,
            title = EXCLUDED.title,
            vote_average = EXCLUDED.vote_average,
            vote_count = EXCLUDED.vote_count,
            popularity = EXCLUDED.popularity,
            trailer_key = COALESCE(EXCLUDED.trailer_key, movies.trailer_key),
            updated_at = now()
        RETURNING id
    """,
        tmdb_id, ml_id,
        detail.get("title", ""), detail.get("original_title"),
        detail.get("overview"), detail.get("tagline"),
        __import__('datetime').date.fromisoformat(detail['release_date']) if detail.get('release_date') else None, detail.get('runtime'),
        detail.get("budget") or 0, detail.get("revenue") or 0,
        detail.get("vote_average"), detail.get("vote_count"),
        detail.get("popularity"), detail.get("poster_path"),
        detail.get("backdrop_path"), trailer_key,
        detail.get("original_language"), detail.get("status"),
        bool(detail.get("adult", False)),
    )

    for g in detail.get("genres", []):
        await conn.execute(
            "INSERT INTO movie_genres (movie_id, genre_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            movie_id, g["id"]
        )

    for kw in detail.get("keywords", {}).get("keywords", []):
        await conn.execute(
            "INSERT INTO keywords (id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            kw["id"], kw["name"]
        )
        await conn.execute(
            "INSERT INTO movie_keywords (movie_id, keyword_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            movie_id, kw["id"]
        )

    credits = detail.get("credits", {})
    for member in credits.get("cast", [])[:20]:
        person_id = await conn.fetchval("""
            INSERT INTO persons (tmdb_id, name, profile_path, known_for_dept)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tmdb_id) DO UPDATE SET name = EXCLUDED.name RETURNING id
        """, member["id"], member.get("name", ""), member.get("profile_path"), "Acting")
        cast_order = member.get("order", 99)
        is_lead = cast_order < 3
        await conn.execute("""
            INSERT INTO movie_cast (movie_id, person_id, character, cast_order, is_lead)
            VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING
        """, movie_id, person_id, member.get("character"), cast_order, is_lead)

    for member in credits.get("crew", []):
        if member.get("job") not in ("Director", "Producer", "Screenplay", "Writer"):
            continue
        person_id = await conn.fetchval("""
            INSERT INTO persons (tmdb_id, name, profile_path, known_for_dept)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tmdb_id) DO UPDATE SET name = EXCLUDED.name RETURNING id
        """, member["id"], member.get("name", ""), member.get("profile_path"),
            "Directing" if member.get("job") == "Director" else "Writing")
        await conn.execute("""
            INSERT INTO movie_crew (movie_id, person_id, job, department)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, movie_id, person_id, member.get("job"), member.get("department"))

    return movie_id


async def download_movielens(data_dir):
    zip_path = data_dir / "ml-latest-small.zip"
    ml_dir = data_dir / "ml-latest-small"
    if not ml_dir.exists():
        logger.info("Downloading MovieLens ml-latest-small...")
        resp = httpx.get(MOVIELENS_URL, follow_redirects=True, timeout=120)
        zip_path.write_bytes(resp.content)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(data_dir)
        logger.info("MovieLens downloaded.")
    links = pd.read_csv(ml_dir / "links.csv")
    links = links.dropna(subset=["tmdbId"])
    links["tmdbId"] = links["tmdbId"].astype(int)
    return dict(zip(links["tmdbId"], links["movieId"]))


async def import_movielens_ratings(conn, data_dir, tmdb_to_internal):
    ml_dir = data_dir / "ml-latest-small"
    links = pd.read_csv(ml_dir / "links.csv").dropna(subset=["tmdbId"])
    links["tmdbId"] = links["tmdbId"].astype(int)
    ml_id_to_tmdb = dict(zip(links["movieId"], links["tmdbId"]))
    ratings = pd.read_csv(ml_dir / "ratings.csv")
    total = len(ratings)
    matched = 0
    dropped = 0
    batch = []
    for _, row in ratings.iterrows():
        tmdb_id = ml_id_to_tmdb.get(int(row["movieId"]))
        if not tmdb_id:
            dropped += 1
            continue
        movie_id = tmdb_to_internal.get(tmdb_id)
        if not movie_id:
            dropped += 1
            continue
        matched += 1
        batch.append((int(row["userId"]), movie_id, float(row["rating"]), int(row["timestamp"])))
        if len(batch) >= 1000:
            await conn.executemany("""
                INSERT INTO movielens_ratings (movielens_user, movie_id, rating, ml_timestamp)
                VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
            """, batch)
            batch = []
    if batch:
        await conn.executemany("""
            INSERT INTO movielens_ratings (movielens_user, movie_id, rating, ml_timestamp)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, batch)
    match_rate = matched / total if total > 0 else 0
    logger.info(f"MovieLens: total={total}, matched={matched}, match_rate={match_rate:.1%}")
    return {"total": total, "matched": matched, "dropped": dropped, "match_rate": match_rate}


async def run_ingestion(target_movies=4000):
    data_dir = Path(settings.model_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Building MovieLens ID map...")
    movielens_map = await download_movielens(data_dir)

    conn = await get_db_conn()
    try:
        tmdb_ids = set()
        endpoints = ["/movie/popular", "/movie/top_rated", "/movie/now_playing", "/movie/upcoming"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for endpoint in endpoints:
                page = 1
                while len(tmdb_ids) < target_movies:
                    try:
                        data = await fetch_tmdb_page(client, endpoint, page)
                        results = data.get("results", [])
                        if not results:
                            break
                        for r in results:
                            if not r.get("adult", False):
                                tmdb_ids.add(r["id"])
                        page += 1
                        if page > data.get("total_pages", 1):
                            break
                        await asyncio.sleep(0.25)
                    except Exception as e:
                        logger.warning(f"Page fetch failed: {e}")
                        break
                logger.info(f"After {endpoint}: {len(tmdb_ids)} unique IDs")

            tmdb_ids_list = list(tmdb_ids)
            tmdb_to_internal = {}
            ingested = 0
            failed = 0

            for i, tmdb_id in enumerate(tmdb_ids_list):
                if i % 50 == 0:
                    logger.info(f"Progress: {i}/{len(tmdb_ids_list)} ({ingested} ok, {failed} failed)")
                detail = await fetch_movie_details(client, tmdb_id)
                if not detail:
                    failed += 1
                    continue
                try:
                    movie_id = await upsert_movie(conn, detail, movielens_map)
                    if movie_id:
                        tmdb_to_internal[tmdb_id] = movie_id
                        ingested += 1
                except Exception as e:
                    logger.warning(f"Upsert failed for {tmdb_id}: {e}")
                    failed += 1
                await asyncio.sleep(0.26)

        logger.info(f"Ingestion complete: {ingested} movies, {failed} failed")

        logger.info("Importing MovieLens ratings...")
        ml_stats = await import_movielens_ratings(conn, data_dir, tmdb_to_internal)

        return {"movies_ingested": ingested, "movies_failed": failed, "movielens": ml_stats}

    finally:
        await conn.close()


