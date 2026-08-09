"""
Evaluation Suite (FR-8)
-----------------------
Offline metrics via leave-one-out evaluation on MovieLens interaction data:

  Precision@K   — fraction of top-K recommendations that are relevant
  Recall@K      — fraction of relevant items appearing in top-K
  NDCG@K        — normalised discounted cumulative gain (position-aware)
  MAP           — mean average precision across all users
  RMSE / MAE    — rating prediction error
  Coverage      — fraction of catalog that appears in recommendations
  Diversity     — mean intra-list cosine distance (higher = more diverse)

Leave-one-out: for each test user, hold out their last positive interaction,
recommend K items, check if held-out item appears.
"""
import asyncio
import logging
import math
from typing import List, Dict, Tuple, Optional

import asyncpg
import numpy as np

from app.core.config import get_ml_settings
from app.services.collab_filter import get_collab_model
from app.services.neural_cf import get_ncf_model
from app.services.hybrid_recommender import hybrid_recommend

logger = logging.getLogger(__name__)
settings = get_ml_settings()

K_VALUES = [5, 10, 20]


def dcg_at_k(relevant: List[int], recommended: List[int], k: int) -> float:
    """Discounted Cumulative Gain @ K."""
    dcg = 0.0
    for i, item in enumerate(recommended[:k]):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)  # log2(rank+1), rank is 0-indexed
    return dcg


def idcg_at_k(n_relevant: int, k: int) -> float:
    """Ideal DCG when all top-K are relevant."""
    return sum(1.0 / math.log2(i + 2) for i in range(min(n_relevant, k)))


def ndcg_at_k(relevant: List[int], recommended: List[int], k: int) -> float:
    idcg = idcg_at_k(len(relevant), k)
    if idcg == 0:
        return 0.0
    return dcg_at_k(relevant, recommended, k) / idcg


def precision_at_k(relevant: List[int], recommended: List[int], k: int) -> float:
    hits = sum(1 for item in recommended[:k] if item in relevant)
    return hits / k


def recall_at_k(relevant: List[int], recommended: List[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for item in recommended[:k] if item in relevant)
    return hits / len(relevant)


def average_precision(relevant: List[int], recommended: List[int], k: int) -> float:
    """Average precision (for MAP computation)."""
    if not relevant:
        return 0.0
    hits, sum_precision = 0, 0.0
    for i, item in enumerate(recommended[:k]):
        if item in relevant:
            hits += 1
            sum_precision += hits / (i + 1)
    return sum_precision / min(len(relevant), k)


async def run_evaluation(conn: asyncpg.Connection, k_max: int = 20) -> dict:
    """
    Full offline evaluation on leave-one-out splits of MovieLens ratings.

    For each MovieLens user (using ML ratings as proxy):
    1. Hold out highest-rated movie (the "positive" label)
    2. Generate recommendations from remaining history
    3. Check if held-out item appears in top-K

    Also computes RMSE/MAE on rating prediction using SVD reconstructed ratings.
    """
    logger.info("Starting offline evaluation...")

    # Get test users: MovieLens users with ≥5 ratings (enough history)
    test_users = await conn.fetch("""
        SELECT movielens_user, COUNT(*) AS n_ratings
        FROM movielens_ratings
        WHERE movie_id IS NOT NULL
        GROUP BY movielens_user
        HAVING COUNT(*) >= 5
        ORDER BY random()
        LIMIT 500
    """)

    if not test_users:
        return {"error": "No test users found. Run ingestion and training first."}

    logger.info(f"Evaluating on {len(test_users)} test users...")

    collab = get_collab_model()
    ncf = get_ncf_model()

    metrics_by_k = {k: {"precision": [], "recall": [], "ndcg": [], "ap": []} for k in K_VALUES}
    rmse_errors = []
    mae_errors = []
    recommended_items_set = set()
    total_catalog = await conn.fetchval("SELECT COUNT(DISTINCT id) FROM movies")

    # For diversity: collect embeddings of recommended items
    diversity_scores = []

    for user_row in test_users:
        ml_user = user_row["movielens_user"]
        user_key = f"ml_{ml_user}"

        # Get all ratings for this user, sorted by rating desc
        ratings = await conn.fetch("""
            SELECT movie_id, rating FROM movielens_ratings
            WHERE movielens_user = $1 AND movie_id IS NOT NULL
            ORDER BY rating DESC, ml_timestamp DESC
        """, ml_user)

        if len(ratings) < 2:
            continue

        # Leave-one-out: hold out top-rated movie
        held_out = ratings[0]["movie_id"]
        held_out_rating = float(ratings[0]["rating"])
        train_movie_ids = [r["movie_id"] for r in ratings[1:]]

        # Ground truth: all movies rated ≥4 (positive threshold)
        relevant = [r["movie_id"] for r in ratings if float(r["rating"]) >= 4.0 and r["movie_id"] != held_out]
        relevant_set = set(relevant + [held_out])  # held-out is definitely relevant

        # Generate recommendations using collaborative filter (primary evaluation model)
        if not collab.is_trained:
            continue

        collab_scores = collab.score_candidates(user_key, [
            r["movie_id"] for r in await conn.fetch(
                "SELECT DISTINCT id FROM movies WHERE id IN (SELECT movie_id FROM movie_embeddings) LIMIT 500"
            )
        ])

        if not collab_scores:
            continue

        recommended = sorted(collab_scores.keys(), key=lambda x: collab_scores[x], reverse=True)
        # Remove held-out from training candidates (fair evaluation)
        recommended = [mid for mid in recommended if mid != held_out]

        # Re-insert held-out at its true predicted position for fair evaluation
        # Actually for LOO: we pretend held-out was never in training, recommend from full catalog
        # and check if it appears in top-K
        all_candidate_scores = dict(collab_scores)
        # Add held-out back as candidate
        if collab.is_trained and held_out in collab.item_index:
            all_candidate_scores[held_out] = collab_scores.get(held_out, 0.0)

        final_ranked = sorted(all_candidate_scores.keys(), key=lambda x: all_candidate_scores[x], reverse=True)

        # Metrics at each K
        for k in K_VALUES:
            top_k = final_ranked[:k]
            metrics_by_k[k]["precision"].append(precision_at_k(list(relevant_set), top_k, k))
            metrics_by_k[k]["recall"].append(recall_at_k(list(relevant_set), top_k, k))
            metrics_by_k[k]["ndcg"].append(ndcg_at_k(list(relevant_set), top_k, k))
            metrics_by_k[k]["ap"].append(average_precision(list(relevant_set), top_k, k))

        recommended_items_set.update(final_ranked[:k_max])

        # RMSE/MAE: predict rating for held-out
        if collab.is_trained and held_out in collab.item_index:
            predicted = all_candidate_scores.get(held_out, 0.0) * 5.0  # scale to 0-5 range
            actual = held_out_rating
            rmse_errors.append((predicted - actual) ** 2)
            mae_errors.append(abs(predicted - actual))

        # Diversity: compute mean pairwise distance in top-10
        top10_ids = final_ranked[:10]
        if len(top10_ids) >= 2:
            emb_rows = await conn.fetch("""
                SELECT embedding FROM movie_embeddings WHERE movie_id = ANY($1)
            """, top10_ids)
            if len(emb_rows) >= 2:
                embs = []
                for r in emb_rows:
                    raw = r["embedding"]
                    if isinstance(raw, str):
                        vec = np.array([float(x) for x in raw.strip("[]").split(",")])
                    else:
                        vec = np.array(raw)
                    embs.append(vec / (np.linalg.norm(vec) + 1e-8))
                embs = np.array(embs)
                # Mean pairwise cosine distance = 1 - cosine similarity
                sim_matrix = embs @ embs.T
                n = len(embs)
                pairs = [(i, j) for i in range(n) for j in range(i+1, n)]
                if pairs:
                    mean_sim = np.mean([sim_matrix[i, j] for i, j in pairs])
                    diversity_scores.append(1.0 - float(mean_sim))

    # Aggregate
    aggregated = {}
    for k in K_VALUES:
        m = metrics_by_k[k]
        aggregated[f"precision_at_{k}"] = np.mean(m["precision"]) if m["precision"] else 0.0
        aggregated[f"recall_at_{k}"] = np.mean(m["recall"]) if m["recall"] else 0.0
        aggregated[f"ndcg_at_{k}"] = np.mean(m["ndcg"]) if m["ndcg"] else 0.0
        aggregated[f"map_at_{k}"] = np.mean(m["ap"]) if m["ap"] else 0.0

    aggregated["rmse"] = math.sqrt(np.mean(rmse_errors)) if rmse_errors else None
    aggregated["mae"] = float(np.mean(mae_errors)) if mae_errors else None
    aggregated["catalog_coverage"] = len(recommended_items_set) / max(total_catalog, 1)
    aggregated["intra_list_diversity"] = float(np.mean(diversity_scores)) if diversity_scores else 0.0
    aggregated["n_test_users"] = len(test_users)

    # Round for readability
    result = {k: round(float(v), 4) if v is not None else None for k, v in aggregated.items()}

    logger.info(f"Evaluation complete: P@10={result['precision_at_10']:.4f}, "
                f"NDCG@10={result['ndcg_at_10']:.4f}, MAP@10={result['map_at_10']:.4f}, "
                f"RMSE={result['rmse']}")

    return result
