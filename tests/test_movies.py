from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.dependencies import get_current_user
from app.models.user import User
import pytest
import io

client = TestClient(app)

@pytest.fixture(scope="module")
def test_user():
    return User(id=1, username="testuser", email="test@example.com", hashed_password="hashedpassword")

@pytest.fixture(scope="module")
def test_movie():
    return {
        "id": "test_movie_id",
        "title": "Test Movie",
        "genre": "Action",
        "director": "Test Director",
        "release_time": "2023-01-01T00:00:00",
        "rating": 0.0,
        "user_id": 1,
        "s3_key": "movies/test_movie_id/test_movie.mp4"
    }

@patch("app.utils.aws_s3.upload_movie")
@patch("app.utils.aws_dynamodb.put_movie")
def test_add_movie(mock_put_movie, mock_upload_movie, test_user):
    app.dependency_overrides[get_current_user] = lambda: test_user
    mock_upload_movie.return_value = None
    mock_put_movie.return_value = None

    response = client.post(
        "/movies/",
        data={
            "title": "New Test Movie",
            "genre": "Comedy",
            "director": "New Test Director",
            "release_time": "2023-02-01T00:00:00"
        },
        files={"file": ("test_movie.mp4", io.BytesIO(b"test content"), "video/mp4")}
    )

    assert response.status_code == 201
    assert response.json()["title"] == "New Test Movie"
    assert response.json()["genre"] == "Comedy"
    mock_upload_movie.assert_called_once()
    mock_put_movie.assert_called_once()

@patch("app.utils.aws_dynamodb.query_movies_by_rating")
def test_list_movies(mock_query_movies):
    mock_query_movies.return_value = [
        {"id": "1", "title": "Movie 1", "rating": 4.5},
        {"id": "2", "title": "Movie 2", "rating": 3.8}
    ]

    response = client.get("/movies/?min_rating=3.5")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["title"] == "Movie 1"
    assert response.json()[1]["title"] == "Movie 2"

@patch("app.utils.aws_dynamodb.query_movies_by_genre")
def test_list_movies_by_genre(mock_query_movies):
    mock_query_movies.return_value = [
        {"id": "1", "title": "Action Movie 1", "genre": "Action"},
        {"id": "2", "title": "Action Movie 2", "genre": "Action"}
    ]

    response = client.get("/movies/genre/Action")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["genre"] == "Action"
    assert response.json()[1]["genre"] == "Action"

@patch("app.utils.aws_dynamodb.get_movie")
def test_get_movie(mock_get_movie, test_movie):
    mock_get_movie.return_value = test_movie

    response = client.get(f"/movies/{test_movie['id']}")
    assert response.status_code == 200
    assert response.json()["title"] == test_movie["title"]

@patch("app.utils.aws_dynamodb.get_movie")
@patch("app.utils.aws_dynamodb.update_movie")
def test_update_movie(mock_update_movie, mock_get_movie, test_user, test_movie):
    app.dependency_overrides[get_current_user] = lambda: test_user
    mock_get_movie.return_value = test_movie
    mock_update_movie.return_value = {**test_movie, "title": "Updated Test Movie"}

    response = client.put(
        f"/movies/{test_movie['id']}",
        json={"title": "Updated Test Movie"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Test Movie"

@patch("app.utils.aws_dynamodb.get_movie")
@patch("app.utils.aws_s3.delete_movie")
@patch("app.utils.aws_dynamodb.delete_movie")
def test_delete_movie(mock_delete_movie_db, mock_delete_movie_s3, mock_get_movie, test_user, test_movie):
    app.dependency_overrides[get_current_user] = lambda: test_user
    mock_get_movie.return_value = test_movie
    mock_delete_movie_s3.return_value = None
    mock_delete_movie_db.return_value = None

    response = client.delete(f"/movies/{test_movie['id']}")
    assert response.status_code == 204
    mock_delete_movie_s3.assert_called_once_with(test_movie['s3_key'])
    mock_delete_movie_db.assert_called_once_with(test_movie['id'])

@patch("app.utils.aws_dynamodb.get_movie")
@patch("app.utils.aws_s3.get_presigned_url")
def test_download_movie(mock_get_presigned_url, mock_get_movie, test_movie):
    mock_get_movie.return_value = test_movie
    mock_get_presigned_url.return_value = "https://test-presigned-url.com"

    response = client.get(f"/movies/{test_movie['id']}/download")
    assert response.status_code == 200
    assert response.json()["download_url"] == "https://test-presigned-url.com"

@patch("app.utils.aws_dynamodb.get_movie")
@patch("app.utils.aws_dynamodb.add_rating")
def test_rate_movie(mock_add_rating, mock_get_movie, test_user, test_movie):
    app.dependency_overrides[get_current_user] = lambda: test_user
    mock_get_movie.return_value = test_movie
    mock_add_rating.return_value = None

    response = client.post(
        f"/movies/{test_movie['id']}/rate",
        json={"rating": 4.5}
    )
    assert response.status_code == 200
    assert response.json()["rating"] == 4.5
    assert response.json()["user_id"] == test_user.id
    assert response.json()["movie_id"] == test_movie["id"]