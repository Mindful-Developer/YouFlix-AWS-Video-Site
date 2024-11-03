from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


class Movie(Base):
    __tablename__ = 'movies'

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    genre = Column(String, nullable=False)
    director = Column(String, nullable=False)
    release_time = Column(DateTime, nullable=False)
    rating = Column(Float, default=0.0)
    s3_key = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)

    user = relationship('User', back_populates='movies')
    comments = relationship('Comment', back_populates='movie')


def get_movie(db, movie_id: str):
    return db.query(Movie).filter(Movie.id == movie_id).first()


def get_recent_movies(db, limit: int = 10):
    return db.query(Movie).order_by(Movie.release_time.desc()).limit(limit).all()


def get_user_movies(db, user_id: int):
    return db.query(Movie).filter(Movie.user_id == user_id).all()


def get_movies_by_genre(db, genre: str):
    return db.query(Movie).filter(Movie.genre == genre).all()


def get_movies_by_rating(db, min_rating: float):
    return db.query(Movie).filter(Movie.rating >= min_rating).all()


def create_movie(db, movie_data: dict):
    db_movie = Movie(**movie_data)
    db.add(db_movie)
    db.commit()
    db.refresh(db_movie)
    return db_movie


def update_movie(db, movie_id: str, movie_data: dict):
    db_movie = get_movie(db, movie_id)
    if db_movie:
        for key, value in movie_data.items():
            setattr(db_movie, key, value)
        db.commit()
        db.refresh(db_movie)
    return db_movie


def delete_movie(db, movie_id: str):
    db_movie = get_movie(db, movie_id)
    if db_movie:
        db.delete(db_movie)
        db.commit()
    return db_movie