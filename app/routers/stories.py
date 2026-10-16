import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..database import get_db
from ..models import Story
from ..schemas import StoryRequest
from ..security import get_current_user


router = APIRouter(
    prefix="/api",
    tags=["Stories"]
)

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "static" / "uploads"
ALLOWED_MEDIA = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp"},
    "audio": {".mp3", ".wav", ".ogg", ".m4a"},
    "video": {".mp4", ".webm", ".mov"},
}
MAX_MEDIA_BYTES = 25 * 1024 * 1024


@router.post("/stories/media", status_code=201)
async def upload_story_media(
    files: list[UploadFile] = File(...),
    current_user=Depends(get_current_user),
):
    """Store multiple images, audio files, or videos for a travel story."""
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one media file.")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="You can upload up to 10 media files per story.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    media_items = []

    for file in files:
        filename = Path(file.filename or "").name
        extension = Path(filename).suffix.lower()
        media_type = next(
            (kind for kind, extensions in ALLOWED_MEDIA.items() if extension in extensions),
            None,
        )

        if not media_type:
            raise HTTPException(status_code=400, detail=f"Unsupported media format: {filename}")

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"The media file is empty: {filename}")

        if len(content) > MAX_MEDIA_BYTES:
            raise HTTPException(status_code=400, detail=f"{filename} is larger than 25 MB.")

        stored_name = f"{uuid.uuid4().hex}{extension}"
        (UPLOAD_DIR / stored_name).write_bytes(content)
        media_items.append({
            "media_url": f"/static/uploads/{stored_name}",
            "media_type": media_type,
        })

    return {"media_items": media_items}


@router.get("/stories")
def list_stories(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return all approved community stories to any authenticated traveller.

    Important: do not look up the current user here. The JWT has already
    been validated by get_current_user(), and the community feed is
    intentionally shared between authenticated users.
    """
    return db.scalars(
        select(Story)
        .where(Story.approved.is_(True))
        .order_by(Story.created_at.desc())
    ).all()


@router.post("/stories", status_code=201)
def add_story(
    payload: StoryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Import here so this route does not affect the public community-feed query.
    from ..crud import get_user_by_email

    user_email = current_user["sub"]
    db_user = get_user_by_email(db, user_email)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    data = payload.model_dump()
    media_items = data.pop("media_items", [])

    if media_items:
        data["media_url"] = media_items[0]["media_url"]
        data["media_type"] = media_items[0]["media_type"]

    data["media_items"] = media_items

    story = Story(**data, user_id=db_user.id)
    db.add(story)
    db.commit()
    db.refresh(story)

    return story
