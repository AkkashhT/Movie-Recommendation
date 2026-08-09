"""
Neural Collaborative Filtering (NCF)
--------------------------------------
Implements the GMF+MLP fusion architecture from
"Neural Collaborative Filtering" (He et al. 2017).

Architecture:
  - GMF branch: element-wise product of user & item embeddings
  - MLP branch: concatenation fed through MLP layers
  - Final: concatenate GMF + MLP outputs → sigmoid → affinity score

Trained on binarised interaction data:
  - Positive: LIKE, WISHLIST_ADD, RATE≥7, VIEW
  - Negative: DISLIKE, RATE≤3
  - Sampled negatives: 4 random uninteracted movies per positive

For a portfolio project this is intentionally readable over GPU-optimised.
"""
import logging
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import asyncpg
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from app.core.config import get_ml_settings

logger = logging.getLogger(__name__)
settings = get_ml_settings()

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class NeuralCF(nn.Module):
    """
    GMF + MLP fusion NCF.
    user_dim/item_dim = embedding dimension per branch.
    mlp_layers = hidden dims for MLP branch.
    """

    def __init__(
        self,
        n_users: int,
        n_items: int,
        gmf_dim: int = 32,
        mlp_dim: int = 32,
        mlp_layers: List[int] = None,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.mlp_layers = mlp_layers or [64, 32, 16]

        # GMF embeddings
        self.gmf_user_emb = nn.Embedding(n_users, gmf_dim, padding_idx=0)
        self.gmf_item_emb = nn.Embedding(n_items, gmf_dim, padding_idx=0)

        # MLP embeddings
        self.mlp_user_emb = nn.Embedding(n_users, mlp_dim, padding_idx=0)
        self.mlp_item_emb = nn.Embedding(n_items, mlp_dim, padding_idx=0)

        # MLP tower
        mlp_in = mlp_dim * 2
        layers = []
        for out_dim in self.mlp_layers:
            layers.extend([nn.Linear(mlp_in, out_dim), nn.ReLU(), nn.Dropout(dropout)])
            mlp_in = out_dim
        self.mlp = nn.Sequential(*layers)

        # Output: concat GMF and MLP final dim → sigmoid
        self.output = nn.Linear(gmf_dim + self.mlp_layers[-1], 1)
        self.sigmoid = nn.Sigmoid()

        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.01)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, user_ids: torch.Tensor, item_ids: torch.Tensor) -> torch.Tensor:
        # GMF branch
        gmf_u = self.gmf_user_emb(user_ids)
        gmf_i = self.gmf_item_emb(item_ids)
        gmf_out = gmf_u * gmf_i  # element-wise product

        # MLP branch
        mlp_u = self.mlp_user_emb(user_ids)
        mlp_i = self.mlp_item_emb(item_ids)
        mlp_in = torch.cat([mlp_u, mlp_i], dim=1)
        mlp_out = self.mlp(mlp_in)

        # Fusion
        concat = torch.cat([gmf_out, mlp_out], dim=1)
        score = self.sigmoid(self.output(concat)).squeeze(1)
        return score


class NCFTrainer:
    def __init__(self):
        self.model: Optional[NeuralCF] = None
        self.user_index: Dict[str, int] = {}   # user_key -> model idx
        self.item_index: Dict[int, int] = {}   # movie_id -> model idx
        self.item_ids: List[int] = []
        self.is_trained = False

    async def train(self, conn: asyncpg.Connection, epochs: int = 20, batch_size: int = 512):
        logger.info("Preparing data for NCF training...")

        # Build interactions: positives from ML + real user data
        ml_rows = await conn.fetch("""
            SELECT 'ml_' || movielens_user::text AS user_key, movie_id,
                   CASE WHEN rating >= 4 THEN 1 ELSE 0 END AS label
            FROM movielens_ratings WHERE movie_id IS NOT NULL
        """)
        real_rows = await conn.fetch("""
            SELECT 'u_' || user_id::text AS user_key, movie_id,
                   CASE WHEN rating >= 7 THEN 1
                        WHEN rating <= 3 THEN 0
                        ELSE NULL END AS label
            FROM ratings WHERE source = 'user'
        """)
        interaction_rows = await conn.fetch("""
            SELECT 'u_' || user_id::text AS user_key, movie_id,
                   CASE
                     WHEN type IN ('LIKE','WISHLIST_ADD') THEN 1
                     WHEN type = 'DISLIKE' THEN 0
                     WHEN type IN ('VIEW','WATCH_TIME','CLICK') THEN 1
                     ELSE NULL
                   END AS label
            FROM user_interactions
            WHERE movie_id IS NOT NULL
              AND type IN ('LIKE','DISLIKE','WISHLIST_ADD','VIEW','WATCH_TIME','CLICK')
        """)

        all_rows = (
            [(r["user_key"], r["movie_id"], r["label"]) for r in ml_rows if r["label"] is not None]
            + [(r["user_key"], r["movie_id"], r["label"]) for r in real_rows if r["label"] is not None]
            + [(r["user_key"], r["movie_id"], r["label"]) for r in interaction_rows if r["label"] is not None]
        )

        if len(all_rows) < 200:
            logger.warning("Not enough interaction data for NCF training.")
            return False

        logger.info(f"NCF training samples: {len(all_rows)}")

        # Build indices (1-indexed, 0 = padding)
        user_keys = list({r[0] for r in all_rows})
        movie_ids = list({r[1] for r in all_rows})
        user_idx = {u: i + 1 for i, u in enumerate(user_keys)}
        item_idx = {m: i + 1 for i, m in enumerate(movie_ids)}

        n_users = len(user_keys) + 1
        n_items = len(movie_ids) + 1

        users_t = torch.tensor([user_idx[r[0]] for r in all_rows], dtype=torch.long)
        items_t = torch.tensor([item_idx[r[1]] for r in all_rows], dtype=torch.long)
        labels_t = torch.tensor([float(r[2]) for r in all_rows], dtype=torch.float32)

        dataset = TensorDataset(users_t, items_t, labels_t)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Model
        model = NeuralCF(n_users=n_users, n_items=n_items).to(DEVICE)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
        criterion = nn.BCELoss()

        # Training loop
        model.train()
        for epoch in range(epochs):
            total_loss = 0.0
            for user_b, item_b, label_b in loader:
                user_b, item_b, label_b = user_b.to(DEVICE), item_b.to(DEVICE), label_b.to(DEVICE)
                optimizer.zero_grad()
                preds = model(user_b, item_b)
                loss = criterion(preds, label_b)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            if (epoch + 1) % 5 == 0:
                logger.info(f"NCF epoch {epoch+1}/{epochs} loss={total_loss/len(loader):.4f}")

        self.model = model
        self.user_index = user_idx
        self.item_index = item_idx
        self.item_ids = movie_ids
        self.is_trained = True

        self.save()
        logger.info("NCF training complete.")
        return True

    def score_candidates(self, user_key: str, candidate_ids: List[int]) -> Dict[int, float]:
        """Inference: predict affinity score for each candidate."""
        if not self.is_trained or self.model is None:
            return {}

        user_int = self.user_index.get(user_key)
        if user_int is None:
            return {}

        valid = [(mid, self.item_index[mid]) for mid in candidate_ids if mid in self.item_index]
        if not valid:
            return {}

        movie_ids_v, item_ints = zip(*valid)
        u_tensor = torch.tensor([user_int] * len(item_ints), dtype=torch.long).to(DEVICE)
        i_tensor = torch.tensor(list(item_ints), dtype=torch.long).to(DEVICE)

        self.model.eval()
        with torch.no_grad():
            scores = self.model(u_tensor, i_tensor).cpu().numpy()

        return {mid: float(s) for mid, s in zip(movie_ids_v, scores)}

    def save(self):
        path = Path(settings.model_dir) / "ncf.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Move model to CPU before pickling
        if self.model:
            self.model = self.model.cpu()
        with open(path, "wb") as f:
            pickle.dump(self, f)
        if self.model:
            self.model = self.model.to(DEVICE)
        logger.info(f"NCF model saved to {path}")

    @classmethod
    def load(cls) -> Optional["NCFTrainer"]:
        path = Path(settings.model_dir) / "ncf.pkl"
        if not path.exists():
            return None
        with open(path, "rb") as f:
            trainer = pickle.load(f)
        if trainer.model:
            trainer.model = trainer.model.to(DEVICE)
        logger.info("NCF model loaded from disk.")
        return trainer


_ncf: Optional[NCFTrainer] = None


def get_ncf_model() -> NCFTrainer:
    global _ncf
    if _ncf is None:
        _ncf = NCFTrainer.load() or NCFTrainer()
    return _ncf


def reload_ncf_model():
    global _ncf
    _ncf = NCFTrainer.load() or NCFTrainer()
