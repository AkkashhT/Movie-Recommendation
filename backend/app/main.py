from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.db.session import engine, Base
from app.api.routes import auth, users, movies, interactions, recommendations, search, admin

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to do — schema managed by init.sql
    yield
    # Shutdown: close engine
    await engine.dispose()


app = FastAPI(
    title="Cinemate API",
    description="Personalized movie recommendation platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(movies.router)
app.include_router(interactions.router)
app.include_router(recommendations.router)
app.include_router(search.router)
app.include_router(admin.router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cinemate-backend"}
