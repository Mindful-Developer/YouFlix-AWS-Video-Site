from datetime import datetime, timezone

from fastapi import FastAPI, Request, Depends, status
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import logging

from database import SessionLocal
from dependencies import get_db, get_current_user, get_current_user_from_cookie
from routers import auth, movies, comments
from utils import aws_dynamodb

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Add db and current_user to request state
        request.state.db = SessionLocal()
        request.state.current_user = await get_current_user_from_cookie(request, request.state.db)
        response = await call_next(request)
        request.state.db.close()
        return response


app.add_middleware(UserMiddleware)

# Mount static files
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")

# Initialize templates
templates = Jinja2Templates(directory="templates")


# Add custom filters to Jinja2 environment
def to_datetime(value):
    if isinstance(value, datetime):
        # Make sure datetime is timezone-aware
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    try:
        # Parse ISO format string and ensure timezone awareness
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


def format_datetime(value):
    dt = to_datetime(value)
    return dt.strftime('%Y-%m-%d %H:%M:%S %Z')


# Add filters to Jinja2 environment
templates.env.filters["to_datetime"] = to_datetime
templates.env.filters["format_datetime"] = format_datetime

app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(comments.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error handler caught: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred"}
    )


@app.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "current_user": request.state.current_user}
    )


@app.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(
        request: Request,
        db: Session = Depends(get_db)
):
    current_user = request.state.current_user
    if not current_user:
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_302_FOUND)

    user_movies = aws_dynamodb.get_movies_by_user(current_user.id)
    user_comments = aws_dynamodb.get_comments_by_user(current_user.id)

    # Ensure all comment timestamps are timezone-aware
    for comment in user_comments:
        if 'timestamp' in comment:
            comment['timestamp'] = to_datetime(comment['timestamp'])

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": request.state.current_user,
            "movies": user_movies,
            "comments": user_comments,
            "now": datetime.now(timezone.utc)
        }
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy"}