from fastapi import FastAPI
from app.routers import auth, movies, comments


app = FastAPI()

app.include_router(auth.router)
app.include_router(movies.router)
app.include_router(comments.router)
