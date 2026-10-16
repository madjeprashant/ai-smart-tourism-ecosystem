from dotenv import load_dotenv

load_dotenv()
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
import re

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, inspect, select
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import CORS_ORIGINS, validate_runtime_configuration
from .database import Base, engine, get_db
from .models import Expense, Story, User
from .schemas import UserRegister
from .crud import create_user, get_user_by_email
from .routers import (
    admin,
    users,
    expenses,
    stories,
    planner,
    food,
    weather,
    chat,
    knowledge,
    common,
    maps,
    hotels,
    restaurants,
)
from .routers.itineraries import router as itineraries_router

APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_configuration()
    Base.metadata.create_all(bind=engine)
    # Lightweight compatibility migration for an existing project database.
    with engine.begin() as connection:
        story_columns = {column["name"] for column in inspect(connection).get_columns("stories")}
        if story_columns and "media_url" not in story_columns:
            connection.execute(text("ALTER TABLE stories ADD COLUMN media_url VARCHAR(300)"))
        if story_columns and "media_type" not in story_columns:
            connection.execute(text("ALTER TABLE stories ADD COLUMN media_type VARCHAR(20)"))
        if story_columns and "media_items" not in story_columns:
            connection.execute(text("ALTER TABLE stories ADD COLUMN media_items JSON"))
        user_columns = {column["name"] for column in inspect(connection).get_columns("users")}
        if user_columns and "username" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
    yield


app = FastAPI(title="AI Smart Tourism Ecosystem", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(common.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(expenses.router)
app.include_router(stories.router)
app.include_router(planner.router)
app.include_router(food.router)
app.include_router(weather.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(itineraries_router)
app.include_router(maps.router)
app.include_router(hotels.router)
app.include_router(restaurants.router)

@app.get("/admin")
def admin_home():
    return FileResponse(APP_DIR / "static" / "admin.html")

@app.get("/")
def home():
    return FileResponse(APP_DIR / "static" / "index.html")