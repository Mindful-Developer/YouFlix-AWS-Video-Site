from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.main import app
from app.dependencies import get_db
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
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword"
    }
    response = client.post("/auth/register", json=user_data)
    assert response.status_code == 201
    return user_data

def test_register_user():
    response = client.post("/auth/register", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "newpassword"
    })
    assert response.status_code == 201
    assert response.json() == {"detail": "User registered successfully"}

def test_register_existing_user(test_user):
    response = client.post("/auth/register", json=test_user)
    assert response.status_code == 400
    assert "Username already registered" in response.json()["detail"]

def test_login_user(test_user):
    response = client.post("/auth/login", data={
        "username": test_user["username"],
        "password": test_user["password"]
    })
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_wrong_password(test_user):
    response = client.post("/auth/login", data={
        "username": test_user["username"],
        "password": "wrongpassword"
    })
    assert response.status_code == 400
    assert "Incorrect username or password" in response.json()["detail"]

def test_login_nonexistent_user():
    response = client.post("/auth/login", data={
        "username": "nonexistentuser",
        "password": "somepassword"
    })
    assert response.status_code == 400
    assert "Incorrect username or password" in response.json()["detail"]