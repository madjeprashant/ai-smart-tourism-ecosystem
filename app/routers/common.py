from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["Common"])

# Serve the VoyageAI frontend from the same FastAPI server.
APP_DIR = Path(__file__).resolve().parent.parent


@router.get("/")
def home():
    return FileResponse(APP_DIR / "static" / "index.html")


@router.get("/api/health")
def health():
    return {
        "status": "Healthy"
    }