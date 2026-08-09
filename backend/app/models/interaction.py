from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime,
    Numeric, ForeignKey, func, Enum as SAEnum, Text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import enum
from app.db.session import Base


class InteractionType(str, enum.Enum):
    CLICK = "CLICK"
    VIEW = "VIEW"
    WATCH_TIME = "WATCH_TIME"
    RATE = "RATE"
    LIKE = "LIKE"
    DISLIKE = "DISLIKE"
    WISHLIST_ADD = "WISHLIST_ADD"
    WISHLIST_REMOVE = "WISHLIST_REMOVE"
    SEARCH_QUERY = "SEARCH_QUERY"


# Interaction weights for embedding updates (positive = signal toward, negative = away)
INTERACTION_WEIGHTS = {
    InteractionType.CLICK: 0.3,
    InteractionType.VIEW: 0.5,
    InteractionType.WATCH_TIME: 0.7,
    InteractionType.RATE: 0.8,       # further modified by actual rating value
    InteractionType.LIKE: 1.0,
    InteractionType.DISLIKE: -0.8,
    InteractionType.WISHLIST_ADD: 0.9,
    InteractionType.WISHLIST_REMOVE: -0.2,
    InteractionType.SEARCH_QUERY: 0.0,  # no embedding update for searches
}


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="SET NULL"))
    type = Column(SAEnum(InteractionType, name="interaction_type"), nullable=False)
    weight = Column(Numeric(4, 2))
    meta = Column("metadata", JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="interactions")
    movie = relationship("Movie")


class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    rating = Column(Numeric(3, 1), nullable=False)
    source = Column(String, default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="ratings")
    movie = relationship("Movie", back_populates="ratings")


class Watchlist(Base):
    __tablename__ = "watchlist"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watchlist")
    movie = relationship("Movie")


class MovieLensRating(Base):
    __tablename__ = "movielens_ratings"

    id = Column(BigInteger, primary_key=True)
    movielens_user = Column(Integer, nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"))
    rating = Column(Numeric(3, 1), nullable=False)
    ml_timestamp = Column(BigInteger)
