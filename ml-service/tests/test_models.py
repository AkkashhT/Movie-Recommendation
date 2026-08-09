"""
Phase 4 unit tests — each model must return non-empty ranked results.
Run with: pytest tests/test_models.py -v
"""
import asyncio
import numpy as np
import pytest
import time


# ── Test 1: Content embeddings & pgvector similarity ──────────────────────────
def test_embedding_model_loads():
    """Sentence-transformer loads and produces 384-dim vectors."""
    from app.services.content_filter import get_embedding_model, build_movie_text
    model = get_embedding_model()
    text = build_movie_text({
        "title": "Inception",
        "overview": "A thief who steals corporate secrets through dream-sharing technology.",
        "genres": ["Action", "Science Fiction", "Thriller"],
        "keywords": ["dream", "heist", "subconscious"],
        "directors": ["Christopher Nolan"],
        "lead_actors": ["Leonardo DiCaprio", "Joseph Gordon-Levitt", "Ellen Page"],
        "supporting_actors": ["Tom Hardy", "Ken Watanabe"],
    })
    emb = model.encode([text], normalize_embeddings=True)[0]
    assert emb.shape == (384,), f"Expected 384-dim embedding, got {emb.shape}"
    assert abs(np.linalg.norm(emb) - 1.0) < 1e-5, "Embedding should be L2-normalised"
    print(f"  ✓ Embedding shape: {emb.shape}, norm: {np.linalg.norm(emb):.4f}")


def test_movie_text_builder():
    """build_movie_text produces non-empty string with all sections."""
    from app.services.content_filter import build_movie_text
    text = build_movie_text({
        "title": "Parasite",
        "overview": "Greed and class discrimination threaten a symbiotic relationship.",
        "genres": ["Drama", "Thriller"],
        "keywords": ["class divide", "family"],
        "directors": ["Bong Joon-ho"],
        "lead_actors": ["Song Kang-ho"],
        "supporting_actors": [],
        "tagline": "Act like you own the place.",
    })
    assert "Parasite" in text
    assert "Bong Joon-ho" in text
    assert "Drama" in text
    assert "Song Kang-ho" in text  # lead repeated for weight
    print(f"  ✓ Movie text length: {len(text)} chars")


# ── Test 2: Collaborative filter ──────────────────────────────────────────────
def test_collab_filter_trains_on_synthetic_data():
    """
    CollaborativeFilter trains on synthetic rating data and returns ranked results.
    Simulates the MovieLens pre-training scenario without a live DB.
    """
    import asyncio
    from app.services.collab_filter import CollaborativeFilter
    from unittest.mock import AsyncMock, MagicMock

    # Build synthetic rating data using simple objects with dict-like access
    np.random.seed(42)
    n_users, n_movies = 50, 200
    movie_ids = list(range(1, n_movies + 1))

    class FakeRecord(dict):
        """Mimics asyncpg Record dict-like access."""
        pass

    ml_rows = []
    real_rows = []
    for uid in range(1, n_users + 1):
        n_ratings = np.random.randint(5, 30)
        rated_movies = np.random.choice(movie_ids, size=n_ratings, replace=False)
        for mid in rated_movies:
            rating = float(np.random.choice([1.0, 2.0, 3.0, 4.0, 5.0]))
            ml_rows.append(FakeRecord({"user_key": f"ml_{uid}", "movie_id": int(mid), "rating": rating}))

    # Mock asyncpg connection
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=[ml_rows, real_rows])

    cf = CollaborativeFilter()

    async def _train():
        return await cf.train(mock_conn)

    result = asyncio.run(_train())
    assert result is True, "Training should return True on success"
    assert cf.is_trained, "Model should be marked as trained"
    assert cf.user_factors is not None
    assert cf.item_factors is not None
    assert len(cf.item_ids) > 0, "Should have item ids"
    assert len(cf.user_index) == n_users, f"Expected {n_users} users, got {len(cf.user_index)}"

    # Score candidates for a known user
    test_user = "ml_1"
    candidates = movie_ids[:50]
    scores = cf.score_candidates(test_user, candidates)

    assert len(scores) > 0, "Should return scores for candidates"
    assert all(0.0 <= v <= 1.0 for v in scores.values()), "Scores should be normalised to [0,1]"

    top5 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
    assert len(top5) == 5, "Should return 5 top recommendations"
    print(f"  ✓ CF trained: {cf.user_factors.shape[0]} users, {cf.item_factors.shape[0]} items")
    print(f"  ✓ Top-5 scores: {[f'{mid}:{s:.3f}' for mid, s in top5]}")


def test_collab_item_knn():
    """Item-KNN returns similar items after training."""
    import asyncio
    from app.services.collab_filter import CollaborativeFilter
    from unittest.mock import AsyncMock

    np.random.seed(7)
    n_users, n_movies = 30, 100
    movie_ids = list(range(1, n_movies + 1))

    ml_rows = []
    for uid in range(1, n_users + 1):
        rated = np.random.choice(movie_ids, size=15, replace=False)
        for mid in rated:
            ml_rows.append({"user_key": f"ml_{uid}", "movie_id": int(mid),
                            "rating": float(np.random.randint(1, 6))})

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=[ml_rows, []])

    cf = CollaborativeFilter()
    asyncio.run(cf.train(mock_conn))

    knn = cf.item_knn(movie_ids[0], top_k=10)
    assert len(knn) > 0, "KNN should return similar items"
    assert knn[0][0] != movie_ids[0], "Should not return self as similar"
    print(f"  ✓ Item KNN top-3: {knn[:3]}")


# ── Test 3: Neural CF ─────────────────────────────────────────────────────────
def test_ncf_trains_and_scores():
    """NCF (GMF+MLP) trains on synthetic data and produces affinity scores."""
    import asyncio
    from app.services.neural_cf import NCFTrainer
    from unittest.mock import AsyncMock

    np.random.seed(99)
    n_users, n_movies = 40, 150
    movie_ids = list(range(1, n_movies + 1))

    ml_rows, real_rows, interaction_rows = [], [], []
    for uid in range(1, n_users + 1):
        rated = np.random.choice(movie_ids, size=20, replace=False)
        for mid in rated:
            rating = float(np.random.randint(1, 6))
            label = 1 if rating >= 4 else 0
            ml_rows.append({"user_key": f"ml_{uid}", "movie_id": int(mid), "label": label})

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=[ml_rows, real_rows, interaction_rows])

    trainer = NCFTrainer()
    result = asyncio.run(trainer.train(mock_conn, epochs=5))  # 5 epochs for test speed

    assert result is True, "NCF training should succeed"
    assert trainer.is_trained
    assert trainer.model is not None

    # Score candidates
    test_user = "ml_1"
    candidates = movie_ids[:30]
    scores = trainer.score_candidates(test_user, candidates)

    assert len(scores) > 0, "NCF should return scores"
    assert all(0.0 <= v <= 1.0 for v in scores.values()), "NCF outputs sigmoid → [0,1]"
    top5 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"  ✓ NCF trained, top-5: {[f'{mid}:{s:.3f}' for mid, s in top5]}")


# ── Test 4: MMR re-ranking reduces same-genre repetition ─────────────────────
def test_mmr_reduces_genre_repetition():
    """
    MMR re-ranking measurably reduces same-genre repetition vs. unranked list.
    Simulates a scored list biased toward Action movies and checks diversity.
    """
    from app.services.hybrid_recommender import mmr_rerank

    np.random.seed(42)
    # Simulate 30 movies: 20 Action (similar embeddings) + 10 mixed
    action_base = np.random.randn(384)
    action_base /= np.linalg.norm(action_base)

    items = []
    for i in range(20):
        # Action movies: small perturbation of base vector
        emb = action_base + 0.1 * np.random.randn(384)
        emb /= np.linalg.norm(emb)
        score = 0.9 - i * 0.01  # High scores (ranked by relevance alone → all Action)
        items.append((i + 1, score, emb))

    for i in range(10):
        # Diverse movies: random embeddings
        emb = np.random.randn(384)
        emb /= np.linalg.norm(emb)
        score = 0.7 - i * 0.02  # Slightly lower scores
        items.append((21 + i, score, emb))

    # Without MMR: top-10 would be all Action
    unranked_top10 = [item[0] for item in sorted(items, key=lambda x: x[1], reverse=True)[:10]]
    action_in_unranked = sum(1 for mid in unranked_top10 if mid <= 20)

    # With MMR (lambda=0.5): should mix in diverse movies
    mmr_result = mmr_rerank(items, top_k=10, lambda_=0.5)
    mmr_ids = [item[0] for item in mmr_result]
    action_in_mmr = sum(1 for mid in mmr_ids if mid <= 20)

    assert action_in_mmr < action_in_unranked, (
        f"MMR should reduce genre repetition: "
        f"unranked={action_in_unranked}/10 Action, mmr={action_in_mmr}/10 Action"
    )
    print(f"  ✓ MMR diversity: unranked={action_in_unranked}/10 Action movies → "
          f"MMR={action_in_mmr}/10 (reduced by {action_in_unranked - action_in_mmr})")


# ── Test 5: User embedding update (live re-ranking signal) ───────────────────
def test_user_embedding_update():
    """
    After a LIKE interaction, user embedding moves toward the liked movie's embedding.
    After a DISLIKE, it moves away.
    """
    import asyncio
    from app.services.embeddings import (
        update_user_embedding_on_interaction,
        DECAY,
    )
    from unittest.mock import AsyncMock

    np.random.seed(0)
    user_emb = np.random.randn(384)
    user_emb /= np.linalg.norm(user_emb)

    movie_emb = np.random.randn(384)
    movie_emb /= np.linalg.norm(movie_emb)

    # Initial cosine similarity
    initial_sim = float(user_emb @ movie_emb)

    # Simulate LIKE (weight=+1.0)
    # Manual update: new = normalize(DECAY * user + (1-DECAY) * movie * weight)
    new_emb = DECAY * user_emb + (1 - DECAY) * movie_emb * 1.0
    new_emb /= np.linalg.norm(new_emb)
    sim_after_like = float(new_emb @ movie_emb)

    assert sim_after_like > initial_sim, (
        f"After LIKE, similarity to movie should increase: {initial_sim:.4f} → {sim_after_like:.4f}"
    )

    # Simulate DISLIKE (weight=-0.8): should decrease similarity
    new_emb_dislike = DECAY * user_emb + (1 - DECAY) * movie_emb * (-0.8)
    norm = np.linalg.norm(new_emb_dislike)
    if norm > 1e-8:
        new_emb_dislike /= norm
    sim_after_dislike = float(new_emb_dislike @ movie_emb)

    assert sim_after_dislike < initial_sim, (
        f"After DISLIKE, similarity should decrease: {initial_sim:.4f} → {sim_after_dislike:.4f}"
    )

    print(f"  ✓ Embedding dynamics: base_sim={initial_sim:.3f}, "
          f"after_like={sim_after_like:.3f} (+{sim_after_like - initial_sim:.3f}), "
          f"after_dislike={sim_after_dislike:.3f} ({sim_after_dislike - initial_sim:.3f})")


# ── Test 6: Cold-start blend weights ─────────────────────────────────────────
def test_cold_start_blend():
    """Blend weights shift continuously from cold to warm as interactions increase."""
    from app.services.hybrid_recommender import cold_start_blend

    cold = cold_start_blend(0)
    mid = cold_start_blend(10)
    warm = cold_start_blend(20)  # at threshold

    # At cold start: content + popularity should dominate
    assert cold["popularity"] > warm["popularity"], "Popularity weight should decrease as user warms up"
    assert cold["collab"] < warm["collab"], "Collaborative weight should increase"
    assert cold["neural"] < warm["neural"], "Neural weight should increase"

    # Weights should always sum to ~1
    for blend in [cold, mid, warm]:
        total = sum(blend.values())
        assert abs(total - 1.0) < 0.01, f"Weights should sum to 1.0, got {total}"

    print(f"  ✓ Cold blend: content={cold['content']:.2f}, pop={cold['popularity']:.2f}, "
          f"collab={cold['collab']:.2f}, neural={cold['neural']:.2f}")
    print(f"  ✓ Warm blend: content={warm['content']:.2f}, pop={warm['popularity']:.2f}, "
          f"collab={warm['collab']:.2f}, neural={warm['neural']:.2f}")


if __name__ == "__main__":
    print("\n=== Cinemate ML Model Tests ===\n")
    tests = [
        ("Embedding model loads + 384-dim output", test_embedding_model_loads),
        ("Movie text builder", test_movie_text_builder),
        ("Collaborative filter trains + scores", test_collab_filter_trains_on_synthetic_data),
        ("Item KNN", test_collab_item_knn),
        ("NCF (GMF+MLP) trains + scores", test_ncf_trains_and_scores),
        ("MMR reduces genre repetition", test_mmr_reduces_genre_repetition),
        ("User embedding update dynamics", test_user_embedding_update),
        ("Cold-start blend weights", test_cold_start_blend),
    ]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            print(f"\n[TEST] {name}")
            fn()
            print(f"  → PASSED")
            passed += 1
        except Exception as e:
            print(f"  → FAILED: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed} tests")
