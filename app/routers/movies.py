from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from uuid import uuid4
from typing import Optional

from app.dependencies import get_db
from app.utils import aws_s3, aws_dynamodb

router = APIRouter(
    prefix="/movies",
    tags=["movies"],
)

templates = Jinja2Templates(directory="app/templates")


@router.get("/upload", response_class=HTMLResponse, name="upload_movie")
async def upload_movie_page(request: Request):
    """Render the upload movie form"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "movie_upload.html",
        {"request": request, "current_user": request.state.current_user}
    )


@router.post("/", name="upload_movie_submit")
async def upload_movie(
        request: Request,
        title: str = Form(...),
        genre: str = Form(...),
        director: str = Form(...),
        release_time: str = Form(...),
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """Handle movie upload submission"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    try:
        movie_id = str(uuid4())
        s3_key = f"movies/{movie_id}/{file.filename}"

        # Upload to S3
        await aws_s3.upload_movie(file.file, s3_key)

        # Store in DynamoDB
        movie_data = {
            "id": movie_id,
            "title": title,
            "genre": genre,
            "director": director,
            "release_time": release_time,
            "rating": 0,
            "user_id": request.state.current_user.id,
            "s3_key": s3_key,
        }
        aws_dynamodb.put_movie(movie_data)

        return RedirectResponse(
            url=f"/movies/{movie_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/browse", response_class=HTMLResponse, name="browse_movies")
async def browse_movies(
        request: Request,
        genre: Optional[str] = None,
        min_rating: Optional[str] = None,  # Change to str to handle empty strings
        db: Session = Depends(get_db)
):
    """Browse movies with optional filters"""
    try:
        # Initialize empty movies list
        movies = []

        # Get movies based on filters
        if genre and genre.strip():
            movies = aws_dynamodb.query_movies_by_genre(genre)
        elif min_rating and min_rating.strip():  # Check if min_rating is not empty
            try:
                rating_value = int(min_rating)
                movies = aws_dynamodb.query_movies_by_rating(rating_value)
            except ValueError:
                movies = aws_dynamodb.scan_movies()  # Invalid rating value, show all movies
        else:
            movies = aws_dynamodb.scan_movies()  # Get all movies if no filters

        # Validate movie data
        validated_movies = []
        for movie in movies:
            if movie and isinstance(movie, dict) and movie.get('id'):
                # Ensure all required fields have default values if missing
                validated_movie = {
                    'id': movie['id'],
                    'title': movie.get('title', 'Untitled'),
                    'genre': movie.get('genre', 'Uncategorized'),
                    'director': movie.get('director', 'Unknown'),
                    'rating': int(movie.get('rating', 0)),
                    'user_id': movie.get('user_id'),
                    'release_time': movie.get('release_time', ''),
                    's3_key': movie.get('s3_key', '')
                }
                validated_movies.append(validated_movie)

        return templates.TemplateResponse(
            "movie_browse.html",
            {
                "request": request,
                "current_user": request.state.current_user,
                "movies": validated_movies,
                "selected_genre": genre,
                "min_rating": min_rating if min_rating and min_rating.strip() else None,
                "error": None
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "movie_browse.html",
            {
                "request": request,
                "current_user": request.state.current_user,
                "movies": [],
                "selected_genre": genre,
                "min_rating": min_rating if min_rating and min_rating.strip() else None,
                "error": "An error occurred while fetching movies."
            }
        )


@router.get("/{movie_id}", response_class=HTMLResponse, name="movie_detail")
async def movie_detail(
        request: Request,
        movie_id: str,
        db: Session = Depends(get_db)
):
    """Show movie details page"""
    movie = aws_dynamodb.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    # Get comments for the movie
    comments = aws_dynamodb.get_comments_by_movie(movie_id)

    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "current_user": request.state.current_user,
            "movie": movie,
            "comments": comments
        }
    )


@router.post("/{movie_id}/rate", name="rate_movie")
async def rate_movie(
    request: Request,
    movie_id: str,
    rating: int = Form(..., ge=1, le=10),
    db: Session = Depends(get_db)
):
    """Handle movie rating submission"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    try:
        aws_dynamodb.add_rating(movie_id, request.state.current_user.id, rating)
        return RedirectResponse(
            url=f"/movies/{movie_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{movie_id}/edit", response_class=HTMLResponse, name="edit_movie")
async def edit_movie_page(
        request: Request,
        movie_id: str,
        db: Session = Depends(get_db)
):
    """Show edit movie form"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    movie = aws_dynamodb.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    if movie['user_id'] != request.state.current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this movie")

    return templates.TemplateResponse(
        "movie_edit.html",
        {
            "request": request,
            "current_user": request.state.current_user,
            "movie": movie
        }
    )


@router.post("/{movie_id}/edit", name="edit_movie_submit")
async def edit_movie_submit(
        request: Request,
        movie_id: str,
        title: str = Form(...),
        genre: str = Form(...),
        director: str = Form(...),
        release_time: str = Form(...),
        db: Session = Depends(get_db)
):
    """Handle movie edit submission"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    movie = aws_dynamodb.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    if movie['user_id'] != request.state.current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this movie")

    try:
        updated_data = {
            "title": title,
            "genre": genre,
            "director": director,
            "release_time": release_time
        }
        aws_dynamodb.update_movie(movie_id, updated_data)
        return RedirectResponse(
            url=f"/movies/{movie_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{movie_id}/delete", name="delete_movie")
async def delete_movie(
        request: Request,
        movie_id: str,
        db: Session = Depends(get_db)
):
    """Handle movie deletion"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    movie = aws_dynamodb.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    if movie['user_id'] != request.state.current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this movie")

    try:
        aws_s3.delete_movie(movie['s3_key'])
        aws_dynamodb.delete_movie(movie_id)
        return RedirectResponse(
            url="/movies/browse",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{movie_id}/download")
async def download_movie(
        request: Request,
        movie_id: str,
        db: Session = Depends(get_db)
):
    """Generate download link for movie"""
    if not request.state.current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    movie = aws_dynamodb.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    try:
        download_url = aws_s3.get_presigned_url(movie['s3_key'])
        return RedirectResponse(url=download_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )