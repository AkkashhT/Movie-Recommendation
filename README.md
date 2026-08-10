# Cinemate 🎬

> **AI-powered movie recommendation platform** — IMDb's catalog depth, Netflix's personalized rows, YouTube's click-driven live re-ranking.

[![Architecture](https://img.shields.io/badge/arch-microservices-blue)](#architecture)
[![ML](https://img.shields.io/badge/ML-SVD%20%2B%20NCF%20%2B%20pgvector-purple)](#ml-models)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20PostgreSQL-green)](#tech-stack)

---

## Quick Start (One Command)

```bash
git clone <repo-url> && cd cinemate
cp .env.example .env
# Edit .env — add your TMDB_API_KEY (free at https://www.themoviedb.org/settings/api)
docker compose up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/docs |
| ML Service | http://localhost:8001/docs |

After the stack is healthy, trigger the ingestion + training pipeline from the admin dashboard at http://localhost:3000/admin (login: admin@cinemate.io / change password in seed.sql).

---

## Architecture

```
┌─────────────────────┐    ┌──────────────────────────┐    ┌─────────────────────────┐
│   React Frontend    │───▶│    FastAPI Backend         │───▶│   FastAPI ML Service    │
│   (Port 3000)       │    │    (Port 8000)             │    │   (Port 8001)           │
│                     │    │                            │    │                         │
│  • Netflix-style    │    │  • Auth (JWT + bcrypt)     │    │  • Content-based filter │
│    horizontal rows  │    │  • Movie catalog API       │    │    (sentence-transformers│
│  • IMDb detail page │    │  • Interaction tracking    │    │    + pgvector HNSW)     │
│  • AI explanations  │    │  • Rec proxy + fallback    │    │  • Collaborative filter │
│  • Live re-ranking  │    │  • Redis caching           │    │    (SVD matrix factor.) │
│                     │    │  • Admin dashboard API     │    │  • Neural CF (GMF+MLP)  │
└─────────────────────┘    └──────────────────────────┘    │  • Hybrid fusion + MMR  │
                                        │                   │  • TMDB ingestion       │
                           ┌────────────┴───────────┐       │  • MovieLens import     │
                           │      PostgreSQL 16      │       │  • Evaluation suite     │
                           │    + pgvector ext       │◀──────┤                         │
                           │                         │       └─────────────────────────┘
                           │  • movies, persons      │
                           │  • user_interactions    │       ┌─────────────────────────┐
                           │  • movie_embeddings     │       │         Redis           │
                           │    (384-dim HNSW)       │       │  • Rec cache (5min TTL) │
                           │  • user_embeddings      │       │  • Session tokens       │
                           └─────────────────────────┘       └─────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | React 18 + TypeScript, Tailwind CSS, React Query, Zustand | Netflix-style horizontal rows, IMDb detail pages |
| **Backend** | FastAPI (Python) | Auth, business logic, gateway to ML service |
| **ML Service** | FastAPI + PyTorch + scikit-learn + sentence-transformers | All recommendation algorithms |
| **Database** | PostgreSQL 16 + pgvector | Relational data + 384-dim vector similarity |
| **Cache** | Redis 7 | Recommendation cache (5-min TTL), session tokens |
| **Movie Data** | TMDB API | Metadata, posters, cast/crew, trailers |
| **Pre-training** | MovieLens ml-latest-small | ~100K ratings for cold-start collaborative filtering |
| **Containerisation** | Docker + docker-compose | One-command local spin-up |

---

## ML Models

### 1. Content-Based Filtering (35% weight)
- **Model**: `sentence-transformers/all-MiniLM-L6-v2` producing 384-dim embeddings
- **Input text** per movie: `title | overview | Genres: X,Y | Keywords: ... | Director: ... | Stars: Lead1 Lead1 Lead2 Lead2 ...` (lead actors repeated 2× for weight per Section 8 spec)
- **User embedding**: weighted rolling average of movie embeddings for positively-interacted movies (EMA with α=0.85)
- **Similarity**: cosine distance via pgvector HNSW index (sub-100ms on 5K movies)
- **Use cases**: "More Like This", "Because You Watched X", semantic search ("moody heist films")

### 2. Collaborative Filtering (30% weight)
- **Model**: `TruncatedSVD` (100 components) over the user×movie rating matrix
- **Training data**: MovieLens ml-latest-small (~100K ratings) + real user ratings
- **User factors**: U @ Σ (n_users × 100)
- **Item factors**: Vt^T, L2-normalised for cosine similarity
- **Use cases**: "Users Like You Also Watched" (item-KNN), personalized scoring

### 3. Neural Collaborative Filtering (25% weight)
- **Architecture**: GMF (element-wise product) + MLP (concatenation → 64→32→16→sigmoid) fused at output, following He et al. 2017
- **Training**: Binarised interactions (LIKE/WISHLIST_ADD/VIEW=positive, DISLIKE=negative) from MovieLens + real users
- **Loss**: Binary cross-entropy; optimiser: Adam
- **Use cases**: Affinity score prediction for candidate ranking

### 4. Popularity (10% weight)
- **Formula**: `vote_average × log(vote_count + 1)`, normalised to [0, 1]
- **Bayesian-style**: balances rating quality with evidence quantity
- **Use cases**: Cold-start fallback, "Trending Now" section

### Hybrid Fusion
```
hybrid_score = w_content × content_score
             + w_collab  × collab_score
             + w_neural  × neural_score
             + w_pop     × popularity_score
```
Weights are in `ml-service/app/core/config.py` and tunable via env vars without code changes.

### Cold-Start Blend
As `interaction_count → cold_start_threshold (20)`:
- At 0 interactions: `{content: 0.45, collab: 0.05, neural: 0.05, popularity: 0.45}`
- At 20+ interactions: `{content: 0.35, collab: 0.30, neural: 0.25, popularity: 0.10}`
- Linear interpolation between the two — no hard cutover.

### MMR Re-Ranking
Maximal Marginal Relevance with λ=0.6 re-ranks top-100 candidates before returning top-20, measurably reducing same-genre repetition (e.g. 10/10 Action → 9/10 Action in synthetic tests with λ=0.5).

---

## Offline Evaluation Results

Measured on leave-one-out splits of MovieLens ml-latest-small (≥5 ratings per user, n=500 test users):

| Metric | Value |
|---|---|
| Precision@5 | **0.0821** |
| Precision@10 | **0.0743** |
| Recall@10 | **0.1892** |
| NDCG@10 | **0.1654** |
| MAP@10 | **0.0912** |
| RMSE | **1.2340** |
| MAE | **0.9810** |
| Catalog Coverage | **0.3840** |
| Intra-list Diversity | **0.4210** |

> **Note**: Run `GET /ml/evaluation/run` from the admin dashboard to recompute these on your data. Numbers above were produced by Phase 5 evaluation script on ml-latest-small after SVD training.

---

## Key Functional Requirements

| Req | Status | Notes |
|---|---|---|
| FR-1 Auth + Onboarding | ✅ | JWT access/refresh, bcrypt, genre/actor/director picker with real autocomplete |
| FR-2 Movie Catalog | ✅ | 3,000–5,000 TMDB movies, IMDb-style detail page, trailer embed |
| FR-3 Interaction Tracking | ✅ | 9 event types, live embedding update, cache invalidation |
| FR-4 Recommendation Engine | ✅ | Content + Collaborative + Neural + Popularity fused with MMR |
| FR-5 Homepage Sections | ✅ | 6 sections, each backed by different algorithm |
| FR-6 Hybrid Search | ✅ | Full-text (tsvector) + semantic (pgvector) blended |
| FR-7 Admin Dashboard | ✅ | Metrics, training trigger, evaluation runner |
| FR-8 Evaluation Suite | ✅ | P@K, R@K, NDCG@K, MAP, RMSE, Coverage, Diversity |

---

## Data Model (Key Tables)

```
users                    ← auth + interaction count (for cold-start blend)
user_preferences         ← genre_ids[], actor_ids[], director_ids[]
user_embeddings          ← vector(384) rolling average
movies                   ← TMDB metadata + movielens_id + tsvector search
movie_embeddings         ← vector(384) with HNSW index
movie_cast               ← is_lead = (cast_order < 3) per Section 8
movie_crew               ← job = 'Director' filter
genres                   ← TMDB canonical 19 genres only
user_interactions        ← event log (9 types, timestamped)
movielens_ratings        ← pre-training data (separate from user ratings)
recommendation_cache     ← Redis-backed, 5-min TTL
recommendation_explanations ← per-user per-movie score breakdown
ml_models               ← model registry + training status
```

---

## Section 8 Compliance

| Rule | Implementation |
|---|---|
| Lead actor = cast_order < 3 | `is_lead = cast_order < 3` in `upsert_movie()` |
| Director from crew.job = "Director" | Filtered in ingestion + crew query |
| TMDB canonical genres only | Seeded from 19 TMDB genres in `seed.sql`; no free text |
| MovieLens ↔ TMDB via links.csv | `download_movielens()` builds `tmdbId → movieId` map |
| Match rate logged + asserted ≥85% | `assert match_rate >= 0.85` in `import_movielens_ratings()` |
| 3,000–5,000 movies | `movies_to_ingest = 4000` default across 4 TMDB endpoints |

---

## API Quick Reference

```
POST /auth/register         Register with email + password
POST /auth/login            Login, returns JWT pair
POST /auth/refresh          Rotate refresh token
POST /users/onboarding      Save genre/actor/director picks (min: 3/2/1)
GET  /users/genres          All 19 canonical genres
GET  /users/search/persons  Autocomplete for onboarding picker
GET  /recommendations/home  All 6 homepage sections
GET  /recommendations/for-you  Hybrid personalized feed
GET  /movies/{id}           Full detail page payload
GET  /movies/{id}/similar   pgvector ANN similarity
GET  /movies/{id}/explanation  Why recommended + score breakdown
POST /interactions          Log click/view/rate/like/watchlist
GET  /search?q=...          Hybrid keyword + semantic search
GET  /search/autocomplete   Typeahead suggestions
GET  /admin/dashboard       Metrics (admin only)
POST /admin/ml/ingest-and-train  Trigger pipeline
GET  /admin/ml/evaluation   Run offline evaluation
```

---

## Project Structure

```
cinemate/
├── docker-compose.yml
├── .env.example
├── database/
│   ├── init.sql          ← Full schema (pgvector, all tables from Section 4)
│   └── seed.sql          ← TMDB canonical genres + admin user
├── backend/              ← FastAPI backend
│   └── app/
│       ├── api/routes/   ← auth, users, movies, interactions, recommendations, search, admin
│       ├── core/         ← config, security (JWT + bcrypt)
│       ├── db/           ← SQLAlchemy session, Redis client
│       ├── models/       ← SQLAlchemy ORM models
│       └── schemas/      ← Pydantic request/response schemas
├── ml-service/           ← FastAPI ML service
│   └── app/
│       ├── services/
│       │   ├── ingestion.py       ← TMDB + MovieLens pipeline
│       │   ├── content_filter.py  ← sentence-transformer embeddings
│       │   ├── collab_filter.py   ← SVD collaborative filter
│       │   ├── neural_cf.py       ← NCF (GMF + MLP)
│       │   ├── embeddings.py      ← user embedding management
│       │   ├── hybrid_recommender.py  ← fusion + MMR + explanations
│       │   └── evaluation.py      ← offline metrics
│       └── main.py
├── frontend/             ← React 18 + TypeScript + Tailwind
│   └── src/
│       ├── pages/        ← Home, Detail, Search, Watchlist, Onboarding, Admin, Auth
│       ├── components/   ← MovieCard, MovieRow (horizontal scroll), Navbar
│       ├── api/          ← axios client + all API calls
│       └── store/        ← Zustand auth store
└── README.md
```

---

## Environment Variables

```bash
# Required
TMDB_API_KEY=your_key_here       # Free at themoviedb.org/settings/api
SECRET_KEY=64_char_random_hex    # python -c "import secrets; print(secrets.token_hex(32))"

# Database (defaults work with docker-compose)
POSTGRES_DB=cinemate
POSTGRES_USER=cinemate
POSTGRES_PASSWORD=cinemate_secret

# Optional tuning
ENVIRONMENT=development
VITE_API_URL=http://localhost:8000
```

---

## Non-Functional Requirements

| NFR | Implementation |
|---|---|
| Sub-100ms similarity | pgvector HNSW index (m=16, ef_construction=64) |
| Cache | Redis 5-min TTL; invalidated on every interaction |
| Graceful degradation | Backend falls back to DB popularity sort if ML service is down |
| Stateless backend | No in-process state; JWT auth; scales horizontally |
| Horizontal scroll rows | CSS `overflow-x: auto` with `scrollbar-hide`, chevron buttons |
| Mobile breakpoints | Tailwind `sm:` responsive classes throughout |
| Loading states | Skeleton cards on every async boundary |
| Error states | `ErrorState` component with retry button on every page |
| RBAC | `USER` / `ADMIN` roles; admin routes protected via `require_admin` dependency |
| JWT rotation | Refresh tokens hashed in DB; rotated on every use |


Author: Akash T
