from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import logging

from app.dependencies import get_db
from app.utils import aws_dynamodb

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/comments",
    tags=["comments"],
)

templates = Jinja2Templates(directory="app/templates")


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
            user_id=int(request.state.current_user.id),  # Explicitly convert to int
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
        comments = aws_dynamodb.get_comments_by_user(int(user_id))  # Explicitly convert to int
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
        logger.debug(f"Getting comment with ID: {comment_id}")
        comment = aws_dynamodb.get_comment(comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="Comment not found")

        logger.debug(f"Retrieved comment: {comment}")

        # Log raw values before conversion
        logger.debug(f"Raw comment user_id: {comment.get('user_id')} (type: {type(comment.get('user_id'))})")
        logger.debug(
            f"Raw current user id: {request.state.current_user.id} (type: {type(request.state.current_user.id)})")

        # Get user IDs with string conversion first
        comment_user_id = str(comment.get('user_id', '')).strip()
        current_user_id = str(request.state.current_user.id).strip()

        logger.debug(f"Comparing user IDs: {comment_user_id} == {current_user_id}")

        # Check if user is authorized to edit using string comparison
        if comment_user_id != current_user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to edit this comment"
            )

        # Handle timestamp comparison
        try:
            logger.debug(f"Raw timestamp: {comment['timestamp']}")
            # Check if timestamp is already a datetime object
            if isinstance(comment['timestamp'], datetime):
                comment_time = comment['timestamp']
            else:
                # If it's a string, parse it
                comment_time = datetime.fromisoformat(str(comment['timestamp']).replace('Z', '+00:00'))

            # Ensure timezone awareness
            if comment_time.tzinfo is None:
                comment_time = comment_time.replace(tzinfo=timezone.utc)

            current_time = datetime.now(timezone.utc)
            logger.debug(f"Time difference: {current_time - comment_time}")

            if (current_time - comment_time) > timedelta(hours=24):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot modify comment after 24 hours"
                )
        except ValueError as e:
            logger.error(f"Timestamp error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing timestamp: {str(e)}"
            )

        # Update the comment
        logger.debug(f"Updating comment with new content: {content}")
        aws_dynamodb.update_comment(comment_id, content)

        # Determine return URL
        referrer = request.headers.get("referer", "")
        logger.debug(f"Referrer URL: {referrer}")

        if "/profile" in referrer:
            return_url = "/profile"
        else:
            return_url = f"/movies/{comment['movie_id']}"

        logger.debug(f"Redirecting to: {return_url}")

        return RedirectResponse(
            url=return_url,
            status_code=status.HTTP_302_FOUND
        )
    except HTTPException as he:
        logger.error(f"HTTP Exception: {he}")
        raise he
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
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

        # Ensure both user IDs are integers for comparison
        comment_user_id = int(comment['user_id'])
        current_user_id = int(request.state.current_user.id)

        # Check if user is authorized to delete
        if comment_user_id != current_user_id:
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