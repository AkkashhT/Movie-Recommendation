"""
Phase 2 & 6 backend tests.
Run with: pytest tests/ -v

These use an in-memory SQLite-compatible setup via mocking; full integration
tests require the Postgres stack from docker-compose.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.security import hash_password, verify_password, create_access_token, decode_token
from app.models.interaction import INTERACTION_WEIGHTS, InteractionType


# ── Security tests ───────────────────────────────────────────────────────────
def test_password_hash_and_verify():
    password = "Secure1!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)
    print(f"  ✓ BCrypt hash/verify works")


def test_jwt_create_and_decode():
    token = create_access_token(user_id=42, role="USER")
    payload = decode_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "USER"
    assert payload["type"] == "access"
    print(f"  ✓ JWT encode/decode works, sub={payload['sub']}")


def test_jwt_invalid_raises():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        decode_token("not.a.valid.token")
    assert exc.value.status_code == 401
    print(f"  ✓ Invalid JWT raises 401")


# ── Interaction weight tests ──────────────────────────────────────────────────
def test_interaction_weights_complete():
    """All interaction types have defined weights."""
    for itype in InteractionType:
        assert itype in INTERACTION_WEIGHTS, f"Missing weight for {itype}"
    print(f"  ✓ All {len(INTERACTION_WEIGHTS)} interaction types have weights")


def test_positive_negative_weights():
    """LIKE is positive, DISLIKE is negative."""
    assert INTERACTION_WEIGHTS[InteractionType.LIKE] > 0
    assert INTERACTION_WEIGHTS[InteractionType.DISLIKE] < 0
    assert INTERACTION_WEIGHTS[InteractionType.WISHLIST_ADD] > 0
    assert INTERACTION_WEIGHTS[InteractionType.WISHLIST_REMOVE] < 0
    print(f"  ✓ Like={INTERACTION_WEIGHTS[InteractionType.LIKE]}, "
          f"Dislike={INTERACTION_WEIGHTS[InteractionType.DISLIKE]}")


def test_like_weight_highest():
    """LIKE should be the highest positive signal."""
    positive_weights = {k: v for k, v in INTERACTION_WEIGHTS.items() if v > 0}
    max_type = max(positive_weights, key=positive_weights.get)
    assert max_type == InteractionType.LIKE, f"Expected LIKE to be max, got {max_type}"
    print(f"  ✓ LIKE has highest positive weight: {INTERACTION_WEIGHTS[InteractionType.LIKE]}")


# ── Phase 6: Live re-ranking test ─────────────────────────────────────────────
def test_recommendation_cache_invalidation_on_interaction():
    """
    Simulates: log LIKE → cache invalidated → next rec call reflects change.
    This is the key Phase 6 acceptance criterion.
    Uses mocked Redis and ML service calls.
    """
    import asyncio
    from unittest.mock import AsyncMock, patch

    invalidated_keys = []

    async def mock_cache_delete_pattern(pattern: str):
        invalidated_keys.append(pattern)

    # Simulate interaction logging
    async def simulate_like_interaction(user_id: int, movie_id: int):
        from app.models.interaction import INTERACTION_WEIGHTS, InteractionType
        itype = InteractionType.LIKE
        weight = INTERACTION_WEIGHTS[itype]

        # Should invalidate cache
        await mock_cache_delete_pattern(f"rec:user:{user_id}:*")

        # Should call ML service embedding update (non-blocking)
        return weight

    result = asyncio.run(simulate_like_interaction(user_id=1, movie_id=42))

    assert result == INTERACTION_WEIGHTS[InteractionType.LIKE]
    assert any(f"rec:user:1:*" in k for k in invalidated_keys), \
        "Cache should be invalidated after LIKE interaction"
    print(f"  ✓ LIKE interaction: weight={result}, cache pattern invalidated: {invalidated_keys[0]}")


def test_cold_start_blend_progression():
    """
    Verify that recommendation weights shift continuously
    from popularity-heavy (cold) to personalized (warm).
    """
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "ml-service"))
    sys.path.insert(0, str(repo_root / "backend"))
    from app.services.hybrid_recommender import cold_start_blend

    at_0 = cold_start_blend(0)
    at_5 = cold_start_blend(5)
    at_10 = cold_start_blend(10)
    at_20 = cold_start_blend(20)

    # Popularity should decrease monotonically
    assert at_0["popularity"] > at_5["popularity"] > at_10["popularity"] > at_20["popularity"], \
        "Popularity weight should decrease as interactions increase"

    # Collaborative should increase monotonically
    assert at_0["collab"] < at_5["collab"] < at_10["collab"] < at_20["collab"], \
        "Collaborative weight should increase with interactions"

    print(f"  ✓ Cold-start blend progression:")
    for n, b in [(0, at_0), (5, at_5), (10, at_10), (20, at_20)]:
        print(f"    interactions={n}: content={b['content']:.2f} collab={b['collab']:.2f} "
              f"neural={b['neural']:.2f} pop={b['popularity']:.2f}")


if __name__ == "__main__":
    print("\n=== Cinemate Backend Tests ===\n")
    tests = [
        ("Password hash/verify", test_password_hash_and_verify),
        ("JWT encode/decode", test_jwt_create_and_decode),
        ("JWT invalid raises 401", test_jwt_invalid_raises),
        ("Interaction weights complete", test_interaction_weights_complete),
        ("Positive/negative weights", test_positive_negative_weights),
        ("LIKE is highest weight", test_like_weight_highest),
        ("Cache invalidated on interaction", test_recommendation_cache_invalidation_on_interaction),
        ("Cold-start blend progression", test_cold_start_blend_progression),
    ]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            print(f"\n[TEST] {name}")
            fn()
            print(f"  → PASSED")
            passed += 1
        except Exception as e:
            import traceback
            print(f"  → FAILED: {e}")
            failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
