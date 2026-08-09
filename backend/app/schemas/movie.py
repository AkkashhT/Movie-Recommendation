from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class GenreSchema(BaseModel):
    id: int
    name: str
    class Config: from_attributes = True


class PersonSchema(BaseModel):
    id: int
    tmdb_id: int
    name: str
    profile_path: Optional[str]
    known_for_dept: Optional[str]
    class Config: from_attributes = True


class CastMemberSchema(BaseModel):
    person: PersonSchema
    character: Optional[str]
    cast_order: int
    is_lead: bool
    class Config: from_attributes = True


class CrewMemberSchema(BaseModel):
    person: PersonSchema
    job: str
    department: Optional[str]
    class Config: from_attributes = True


class MovieCard(BaseModel):
    """Lightweight movie for cards/rows"""
    id: int
    tmdb_id: int
    title: str
    poster_path: Optional[str]
    vote_average: Optional[Decimal]
    release_date: Optional[date]
    genres: List[GenreSchema] = []
    class Config: from_attributes = True


class MovieDetail(BaseModel):
    """Full movie detail page payload"""
    id: int
    tmdb_id: int
    title: str
    original_title: Optional[str]
    overview: Optional[str]
    tagline: Optional[str]
    release_date: Optional[date]
    runtime: Optional[int]
    vote_average: Optional[Decimal]
    vote_count: Optional[int]
    popularity: Optional[Decimal]
    poster_path: Optional[str]
    backdrop_path: Optional[str]
    trailer_key: Optional[str]
    language: Optional[str]
    genres: List[GenreSchema] = []
    cast: List[CastMemberSchema] = []
    directors: List[PersonSchema] = []
    keywords: List[str] = []

    # User-specific fields (None for unauthenticated)
    user_rating: Optional[float] = None
    in_watchlist: Optional[bool] = None
    user_liked: Optional[bool] = None

    class Config: from_attributes = True


class RecommendedMovie(BaseModel):
    """Movie card + recommendation metadata"""
    movie: MovieCard
    hybrid_score: float
    content_score: Optional[float] = None
    collab_score: Optional[float] = None
    neural_score: Optional[float] = None
    popularity_score: Optional[float] = None
    explanation: str


class HomeSection(BaseModel):
    section_key: str
    title: str
    items: List[RecommendedMovie]
    anchor_movie: Optional[MovieCard] = None  # for "Because you watched X"


class HomepageResponse(BaseModel):
    sections: List[HomeSection]
    user_interaction_count: int
    is_cold_start: bool


class SearchResult(BaseModel):
    movies: List[MovieCard]
    total: int
    query: str
    semantic_used: bool


class InteractionRequest(BaseModel):
    movie_id: int
    type: str  # InteractionType value
    weight: Optional[float] = None
    metadata: Optional[dict] = None


class WatchlistResponse(BaseModel):
    movie: MovieCard
    added_at: datetime
    class Config: from_attributes = True
