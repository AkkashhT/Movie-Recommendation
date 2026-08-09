from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date, Numeric,
    BigInteger, Text, func, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import TSVECTOR, ARRAY
from sqlalchemy.orm import relationship
from app.db.session import Base


class Genre(Base):
    __tablename__ = "genres"
    id = Column(Integer, primary_key=True)  # TMDB genre id
    name = Column(String, unique=True, nullable=False)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=False, index=True)
    movielens_id = Column(Integer, index=True)
    title = Column(String, nullable=False)
    original_title = Column(String)
    overview = Column(Text)
    tagline = Column(String)
    release_date = Column(Date)
    runtime = Column(Integer)
    budget = Column(BigInteger)
    revenue = Column(BigInteger)
    vote_average = Column(Numeric(4, 2))
    vote_count = Column(Integer)
    popularity = Column(Numeric(10, 4))
    poster_path = Column(String)
    backdrop_path = Column(String)
    trailer_key = Column(String)
    language = Column(String)
    status = Column(String)
    adult = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    genres = relationship("Genre", secondary="movie_genres", lazy="select")
    cast = relationship("MovieCast", back_populates="movie", order_by="MovieCast.cast_order")
    crew = relationship("MovieCrew", back_populates="movie")
    keywords = relationship("Keyword", secondary="movie_keywords", lazy="select")
    ratings = relationship("Rating", back_populates="movie")


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True)
    tmdb_id = Column(Integer, unique=True, nullable=False)
    name = Column(String, nullable=False)
    profile_path = Column(String)
    biography = Column(Text)
    known_for_dept = Column(String)


class MovieCast(Base):
    __tablename__ = "movie_cast"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    character = Column(String)
    cast_order = Column(Integer, nullable=False)
    is_lead = Column(Boolean, nullable=False)  # cast_order < 3

    movie = relationship("Movie", back_populates="cast")
    person = relationship("Person")


class MovieCrew(Base):
    __tablename__ = "movie_crew"

    id = Column(Integer, primary_key=True)
    movie_id = Column(Integer, ForeignKey("movies.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    job = Column(String, nullable=False)
    department = Column(String)

    movie = relationship("Movie", back_populates="crew")
    person = relationship("Person")


class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)


# Association tables (no ORM class needed, but defined for FK references)
from sqlalchemy import Table
from app.db.session import Base as _Base

movie_genres_table = Table(
    "movie_genres", _Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True,
)

movie_keywords_table = Table(
    "movie_keywords", _Base.metadata,
    Column("movie_id", Integer, ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True),
    Column("keyword_id", Integer, ForeignKey("keywords.id", ondelete="CASCADE"), primary_key=True),
    extend_existing=True,
)
