from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta, timezone

from database import Base


class Comment(Base):
    __tablename__ = 'comments'

    id = Column(Integer, primary_key=True, index=True)
    content = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    movie_id = Column(String, ForeignKey('movies.id'), nullable=False)

    user = relationship('User', back_populates='comments')
    movie = relationship('Movie', back_populates='comments')


def get_comment(db, comment_id: int):
    return db.query(Comment).filter(Comment.id == comment_id).first()


def get_comments_for_movie(db, movie_id: str):
    return db.query(Comment).filter(Comment.movie_id == movie_id).order_by(Comment.timestamp.desc()).all()


def get_user_comments(db, user_id: int):
    return db.query(Comment).filter(Comment.user_id == user_id).order_by(Comment.timestamp.desc()).all()


def create_comment(db, comment_data: dict):
    db_comment = Comment(**comment_data)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment


def update_comment(db, comment_id: int, new_content: str, user_id: int):
    db_comment = get_comment(db, comment_id)
    if db_comment and db_comment.user_id == user_id:
        time_diff = datetime.now(timezone.utc) - db_comment.timestamp
        if time_diff <= timedelta(hours=24):
            db_comment.content = new_content
            db.commit()
            db.refresh(db_comment)
            return db_comment
    return None


def delete_comment(db, comment_id: int, user_id: int):
    db_comment = get_comment(db, comment_id)
    if db_comment and db_comment.user_id == user_id:
        db.delete(db_comment)
        db.commit()
        return db_comment
    return None