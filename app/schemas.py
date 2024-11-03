from pydantic import BaseModel, EmailStr
from datetime import datetime


# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(UserBase):
    id: int
    is_active: bool

    class Config:
        orm_mode = True


# Movie Schemas
class MovieBase(BaseModel):
    title: str
    genre: str
    director: str
    release_time: datetime


class MovieCreate(MovieBase):
    pass


class MovieUpdate(BaseModel):
    title: str | None = None
    genre: str | None = None
    director: str | None = None
    release_time: str | None = None


class MovieOut(MovieBase):
    id: str
    user_id: int
    rating: float

    class Config:
        orm_mode = True


# Comment Schemas
class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    movie_id: str


class CommentUpdate(BaseModel):
    content: str


class CommentOut(CommentBase):
    id: int
    user_id: int
    movie_id: str
    timestamp: datetime

    class Config:
        orm_mode = True


# Rating Schemas
class RatingBase(BaseModel):
    rating: float


class RatingCreate(RatingBase):
    movie_id: str


class RatingOut(RatingBase):
    id: int
    user_id: int
    movie_id: str

    class Config:
        orm_mode = True