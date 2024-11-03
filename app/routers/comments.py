from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from dependencies import get_db
from utils import aws_dynamodb

router = APIRouter(
    prefix="/comments",
    tags=["comments"],
)

templates = Jinja2Templates(directory="templates")


@router.post("/add", name="add_comment")
async def add_comment(
        request: Request,
        movie_id: str = Form(...),
        content: str = Form(...),
        db: Session = Depends(get_db)
):
    """Add a new comment to a movie"""
    if not request.state.current_user:
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_302_FOUND
        )

    try:
        # Add comment to DynamoDB
        aws_dynamodb.add_comment(
            movie_id=movie_id,
            user_id=request.state.current_user.id,
            content=content
        )

        return RedirectResponse(
            url=f"/movies/{movie_id}",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/movie/{movie_id}", response_class=HTMLResponse, name="movie_comments")
async def get_movie_comments(
        request: Request,
        movie_id: str,
        db: Session = Depends(get_db)
):
    """Get all comments for a movie"""
    try:
        comments = aws_dynamodb.get_comments_by_movie(movie_id)
        return templates.TemplateResponse(
            "partials/comments_list.html",
            {
                "request": request,
                "comments": comments,
                "current_user": request.state.current_user,
                "movie_id": movie_id,
                "now": datetime.now(timezone.utc)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/user/{user_id}", response_class=HTMLResponse, name="user_comments")
async def get_user_comments(
        request: Request,
        user_id: int,
        db: Session = Depends(get_db)
):
    """Get all comments by a user"""
    try:
        comments = aws_dynamodb.get_comments_by_user(user_id)
        return templates.TemplateResponse(
            "partials/user_comments.html",
            {
                "request": request,
                "comments": comments,
                "current_user": request.state.current_user,
                "now": datetime.now(timezone.utc)
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{comment_id}/edit", name="edit_comment")
async def edit_comment(
        request: Request,
        comment_id: str,
        content: str = Form(...),
        db: Session = Depends(get_db)
):
    """Edit an existing comment"""
    if not request.state.current_user:
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_302_FOUND
        )

    try:
        # Get the comment
        comment = aws_dynamodb.get_comment(comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        # Check if user is authorized to edit
        if comment['user_id'] != request.state.current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to edit this comment"
            )

        # Check if comment is within 24-hour edit window
        comment_time = datetime.fromisoformat(comment['timestamp'].replace('Z', '+00:00'))
        time_diff = datetime.now(timezone.utc) - comment_time
        if time_diff > timedelta(hours=24):
            raise HTTPException(
                status_code=400,
                detail="Cannot modify comment after 24 hours"
            )

        # Update the comment
        aws_dynamodb.update_comment(comment_id, content)

        return RedirectResponse(
            url=f"/movies/{comment['movie_id']}",
            status_code=status.HTTP_302_FOUND
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{comment_id}/delete", name="delete_comment")
async def delete_comment(
        request: Request,
        comment_id: str,
        db: Session = Depends(get_db)
):
    """Delete a comment"""
    if not request.state.current_user:
        return RedirectResponse(
            url="/auth/login",
            status_code=status.HTTP_302_FOUND
        )

    try:
        # Get the comment
        comment = aws_dynamodb.get_comment(comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        # Check if user is authorized to delete
        if comment['user_id'] != request.state.current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to delete this comment"
            )

        # Delete the comment
        aws_dynamodb.delete_comment(comment_id)

        return RedirectResponse(
            url=f"/movies/{comment['movie_id']}",
            status_code=status.HTTP_302_FOUND
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )