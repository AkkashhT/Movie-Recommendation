"""
Collaborative Filtering — Matrix Factorization (SVD/SVD++)
-----------------------------------------------------------
Uses scikit-learn TruncatedSVD over the user-item rating matrix built from:
  - MovieLens ml-latest-small ratings (pre-training)
  - Real user ratings accumulated over time

Produces:
  - User latent factors (U @ Sigma)
  - Item latent factors (Vt)

For recommendation: score candidates as dot-product of user factor and item factor.
Falls back to item-item KNN cosine similarity for "users like you also watched."

Model serialised to disk as .npz for fast reload without retraining.
"""
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from app.core.config import get_ml_settings

logger = logging.getLogger(__name__)
settings = get_ml_settings()


class CollaborativeFilter:
    """
    SVD-based collaborative filter.

    Attributes:
        user_factors: (n_users, n_components) — U @ Sigma
        item_factors: (n_items, n_components) — Vt^T (normalised)
        user_index: {internal_user_id or movielens_user: row_idx}
        item_index: {movie_id: col_idx}
        item_ids: [movie_id at col_idx i]
    """

    N_COMPONENTS = 100  # latent dimensions for SVD

    def __init__(self):
        self.user_factors: Optional[np.ndarray] = None
        self.item_factors: Optional[np.ndarray] = None
        self.user_index: Dict[str, int] = {}
        self.item_index: Dict[int, int] = {}
        self.item_ids: List[int] = []
        self.is_trained = False

    async def train(self, conn: asyncpg.Connection):
        """
        Build rating matrix from both MovieLens (pre-training) and real user ratings,
        then fit TruncatedSVD.
        """
        logger.info("Fetching ratings for collaborative filter training...")

        # Combine MovieLens ratings (prefix 'ml_') with real user ratings (prefix 'u_')
        ml_ratings = await conn.fetch("""
            SELECT 'ml_' || movielens_user::text AS user_key, movie_id, rating
            FROM movielens_ratings
            WHERE movie_id IS NOT NULL
        """)
        real_ratings = await conn.fetch("""
            SELECT 'u_' || user_id::text AS user_key, movie_id, rating
            FROM ratings
            WHERE source = 'user'
        """)

        all_ratings = list(ml_ratings) + list(real_ratings)
        if len(all_ratings) < 100:
            logger.warning("Not enough ratings for collaborative filter. Need at least 100.")
            return False

        logger.info(f"Total ratings for training: {len(all_ratings)}")

        # Build index mappings
        user_keys = list({r["user_key"] for r in all_ratings})
        movie_ids = list({r["movie_id"] for r in all_ratings})

        user_idx = {u: i for i, u in enumerate(user_keys)}
        item_idx = {m: i for i, m in enumerate(movie_ids)}

        # Build sparse matrix
        row_idxs, col_idxs, values = [], [], []
        for r in all_ratings:
            row_idxs.append(user_idx[r["user_key"]])
            col_idxs.append(item_idx[r["movie_id"]])
            values.append(float(r["rating"]))

        matrix = csr_matrix(
            (values, (row_idxs, col_idxs)),
            shape=(len(user_keys), len(movie_ids))
        )

        logger.info(f"Rating matrix: {matrix.shape}, density={matrix.nnz / (matrix.shape[0] * matrix.shape[1]):.4f}")

        # SVD
        n_components = min(self.N_COMPONENTS, min(matrix.shape) - 1)
        svd = TruncatedSVD(n_components=n_components, random_state=42)
        user_factors = svd.fit_transform(matrix)  # (n_users, k)
        item_factors = svd.components_.T          # (n_items, k)

        # L2-normalize item factors for cosine similarity
        item_factors = normalize(item_factors, norm="l2")
        user_factors_norm = normalize(user_factors, norm="l2")

        self.user_factors = user_factors
        self.item_factors = item_factors
        self.user_index = user_idx
        self.item_index = item_idx
        self.item_ids = movie_ids
        self.is_trained = True

        # Store explained variance for monitoring
        explained_var = svd.explained_variance_ratio_.sum()
        logger.info(f"SVD trained: {n_components} components, explained_var={explained_var:.3f}")

        self.save()
        return True

    def get_user_factor(self, user_key: str) -> Optional[np.ndarray]:
        idx = self.user_index.get(user_key)
        if idx is None:
            return None
        return self.user_factors[idx]

    def score_candidates(
        self,
        user_key: str,
        candidate_ids: List[int],
    ) -> Dict[int, float]:
        """Score candidates for a user via dot-product in latent space."""
        if not self.is_trained:
            return {}
        user_vec = self.get_user_factor(user_key)
        if user_vec is None:
            # Cold-start: return 0 (will be blended with other signals)
            return {mid: 0.0 for mid in candidate_ids}

        # Gather item vectors for candidates
        candidate_indices = [self.item_index[mid] for mid in candidate_ids if mid in self.item_index]
        candidate_movie_ids = [mid for mid in candidate_ids if mid in self.item_index]

        if not candidate_indices:
            return {}

        item_vecs = self.item_factors[candidate_indices]  # (k_cands, n_components)
        scores = item_vecs @ user_vec                      # (k_cands,)

        # Normalise to [0, 1]
        if scores.max() > scores.min():
            scores = (scores - scores.min()) / (scores.max() - scores.min())

        return {mid: float(s) for mid, s in zip(candidate_movie_ids, scores)}

    def item_knn(self, movie_id: int, top_k: int = 50) -> List[Tuple[int, float]]:
        """Item-item similarity for 'users who liked X also liked…'"""
        if not self.is_trained or movie_id not in self.item_index:
            return []
        idx = self.item_index[movie_id]
        anchor = self.item_factors[idx]
        sims = self.item_factors @ anchor  # cosine similarity (factors already L2-norm'd)
        top_indices = np.argsort(sims)[::-1][1: top_k + 1]
        return [(self.item_ids[i], float(sims[i])) for i in top_indices]

    def save(self):
        path = Path(settings.model_dir) / "collab_filter.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)
        logger.info(f"Collaborative filter saved to {path}")

    @classmethod
    def load(cls) -> Optional["CollaborativeFilter"]:
        path = Path(settings.model_dir) / "collab_filter.pkl"
        if not path.exists():
            return None
        with open(path, "rb") as f:
            model = pickle.load(f)
        logger.info("Collaborative filter loaded from disk.")
        return model


# Singleton
_collab_model: Optional[CollaborativeFilter] = None


def get_collab_model() -> CollaborativeFilter:
    global _collab_model
    if _collab_model is None:
        _collab_model = CollaborativeFilter.load() or CollaborativeFilter()
    return _collab_model


def reload_collab_model():
    global _collab_model
    _collab_model = CollaborativeFilter.load() or CollaborativeFilter()
