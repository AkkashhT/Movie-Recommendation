import asyncio
import random
import logging
import asyncpg
from app.core.config import get_ml_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_ml_settings()

SYNTHETIC_PROFILES = [
    {"name": "action_fan",      "genres": [28, 12, 53]},
    {"name": "scifi_geek",      "genres": [878, 28, 12]},
    {"name": "drama_lover",     "genres": [18, 10749, 36]},
    {"name": "comedy_buff",     "genres": [35, 10751, 10749]},
    {"name": "horror_junkie",   "genres": [27, 53, 9648]},
    {"name": "arthouse_fan",    "genres": [18, 99, 36]},
    {"name": "thriller_seeker", "genres": [53, 80, 9648]},
    {"name": "fantasy_world",   "genres": [14, 12, 16]},
    {"name": "crime_watcher",   "genres": [80, 53, 18]},
    {"name": "animation_fan",   "genres": [16, 10751, 14]},
    {"name": "romance_seeker",  "genres": [10749, 35, 18]},
    {"name": "war_history",     "genres": [10752, 36, 18]},
    {"name": "western_buff",    "genres": [37, 28, 12]},
    {"name": "music_lover",     "genres": [10402, 18, 99]},
    {"name": "mixed_1",         "genres": [28, 878, 18, 35]},
    {"name": "mixed_2",         "genres": [53, 27, 9648, 80]},
    {"name": "mixed_3",         "genres": [14, 12, 35, 16]},
    {"name": "cinephile_1",     "genres": [18, 36, 99, 10752]},
    {"name": "cinephile_2",     "genres": [9648, 53, 18, 80]},
    {"name": "blockbuster_fan", "genres": [28, 12, 878, 14]},
    {"name": "indie_watcher",   "genres": [18, 35, 10402]},
    {"name": "family_viewer",   "genres": [10751, 16, 14, 35]},
    {"name": "adventure_seeker","genres": [12, 28, 14]},
    {"name": "mystery_fan",     "genres": [9648, 80, 53]},
    {"name": "eclectic_viewer", "genres": [18, 878, 35, 27]},
]

HASH = "$2b$12$rGPCfNIsmqiC0UsejhJHvOtTs390W7lTHUuSGWlgUSl0UcFQbauIO"


async def main():
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    created = 0

    actors = await conn.fetch(
        "SELECT id FROM persons WHERE known_for_dept = 'Acting' LIMIT 10"
    )
    directors = await conn.fetch(
        "SELECT id FROM persons WHERE known_for_dept = 'Directing' LIMIT 5"
    )
    actor_ids = [r["id"] for r in actors]
    director_ids = [r["id"] for r in directors]

    for i, profile in enumerate(SYNTHETIC_PROFILES):
        username = f"synth_{profile['name']}"
        email = f"{username}@synthetic.cinemate.io"
        genre_ids = profile["genres"]

        existing = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1", email
        )
        if existing:
            logger.info(f"Skipping existing user: {username}")
            continue

        uid = await conn.fetchval("""
            INSERT INTO users (email, username, hashed_password, role, onboarding_done, interaction_count)
            VALUES ($1, $2, $3, 'USER', true, 0) RETURNING id
        """, email, username, HASH)

        await conn.execute("""
            INSERT INTO user_preferences (user_id, favorite_genre_ids, favorite_actor_ids, favorite_director_ids)
            VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING
        """, uid, genre_ids, actor_ids[:3], director_ids[:2])

        movies = await conn.fetch("""
            SELECT m.id, m.vote_average FROM movies m
            JOIN movie_genres mg ON mg.movie_id = m.id
            WHERE mg.genre_id = ANY($1)
            ORDER BY m.vote_average DESC NULLS LAST
            LIMIT 25
        """, genre_ids)

        for movie in movies:
            rating = round(random.uniform(5, 10), 1)
            await conn.execute("""
                INSERT INTO user_interactions (user_id, movie_id, type, weight)
                VALUES ($1, $2, 'VIEW', 0.5) ON CONFLICT DO NOTHING
            """, uid, movie["id"])
            await conn.execute("""
                INSERT INTO ratings (user_id, movie_id, rating, source)
                VALUES ($1, $2, $3, 'synthetic') ON CONFLICT (user_id, movie_id) DO NOTHING
            """, uid, movie["id"], rating)
            if rating >= 7.0:
                await conn.execute("""
                    INSERT INTO user_interactions (user_id, movie_id, type, weight)
                    VALUES ($1, $2, 'LIKE', 1.0) ON CONFLICT DO NOTHING
                """, uid, movie["id"])

        await conn.execute(
            "UPDATE users SET interaction_count = $1 WHERE id = $2",
            len(movies) * 2, uid
        )
        created += 1
        logger.info(f"Created: {username} ({len(movies)} movies)")

    await conn.close()
    print(f"Done! Created {created} synthetic users.")


if __name__ == "__main__":
    asyncio.run(main())
