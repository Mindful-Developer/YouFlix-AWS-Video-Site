from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.main import app
from app.dependencies import get_db, get_current_user
from app.models.user import User
from app.models.comment import Comment
from datetime import datetime, timedelta
import pytest


SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(scope="module")
def test_user():
    db = TestingSessionLocal()
    user = User(username="testuser", email="test@example.com", hashed_password="hashedpassword")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user

@pytest.fixture(scope="module")
def test_movie():
    return {"id": "test_movie_id", "title": "Test Movie"}

@pytest.fixture(scope="function")
def test_comment(test_user, test_movie):
    db = TestingSessionLocal()
    comment = Comment(content="Test comment", user_id=test_user.id, movie_id=test_movie["id"])
    db.add(comment)
    db.commit()
    db.refresh(comment)
    db.close()
    return comment

def test_add_comment(test_user, test_movie):
    app.dependency_overrides[get_current_user] = lambda: test_user
    response = client.post("/comments/", json={
        "content": "New test comment",
        "movie_id": test_movie["id"]
    })
    assert response.status_code == 201
    assert response.json()["content"] == "New test comment"
    assert response.json()["user_id"] == test_user.id
    assert response.json()["movie_id"] == test_movie["id"]

def test_get_comments(test_movie, test_comment):
    response = client.get(f"/comments/movie/{test_movie['id']}")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["content"] == test_comment.content

def test_update_comment_within_24_hours(test_user, test_comment):
    app.dependency_overrides[get_current_user] = lambda: test_user
    response = client.put(f"/comments/{test_comment.id}", json={
        "content": "Updated test comment"
    })
    assert response.status_code == 200
    assert response.json()["content"] == "Updated test comment"

def test_update_comment_after_24_hours(test_user, test_comment):
    app.dependency_overrides[get_current_user] = lambda: test_user
    db = TestingSessionLocal()
    comment = db.query(Comment).filter(Comment.id == test_comment.id).first()
    comment.timestamp = datetime.utcnow() - timedelta(hours=25)
    db.commit()
    db.close()

    response = client.put(f"/comments/{test_comment.id}", json={
        "content": "Updated test comment"
    })
    assert response.status_code == 400
    assert "Cannot modify comment after 24 hours" in response.json()["detail"]

def test_update_comment_unauthorized_user(test_comment):
    unauthorized_user = User(id=999, username="unauthorized", email="unauthorized@example.com", hashed_password="hashedpassword")
    app.dependency_overrides[get_current_user] = lambda: unauthorized_user
    response = client.put(f"/comments/{test_comment.id}", json={
        "content": "Unauthorized update"
    })
    assert response.status_code == 403
    assert "Not authorized to update this comment" in response.json()["detail"]