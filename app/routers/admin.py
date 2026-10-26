from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense, Story, Trip, User
from ..security import get_current_admin
from ..services.knowledge_base import ai_dependencies_available, ai_is_configured, COMMUNITY_STATE_FILE

router = APIRouter(prefix="/api/admin", tags=["Administration"] )


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "created_at": user.created_at,
    }


def _story_dict(story: Story) -> dict:
    return {
        "id": story.id,
        "author": story.author,
        "destination": story.destination,
        "title": story.title,
        "content": story.content,
        "media_url": story.media_url,
        "media_type": story.media_type,
        "media_items": story.media_items or [],
        "approved": bool(story.approved),
        "user_id": story.user_id,
        "created_at": story.created_at,
    }


@router.get("/me")
def admin_me(admin: User = Depends(get_current_admin)):
    return {"id": admin.id, "email": admin.email, "username": admin.username, "role": admin.role}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0
    total_stories = db.scalar(select(func.count()).select_from(Story)) or 0
    pending_stories = db.scalar(select(func.count()).select_from(Story).where(Story.approved.is_(False))) or 0
    approved_stories = db.scalar(select(func.count()).select_from(Story).where(Story.approved.is_(True))) or 0
    total_trips = db.scalar(select(func.count()).select_from(Trip)) or 0
    total_expenses = db.scalar(select(func.count()).select_from(Expense)) or 0
    total_expense_amount = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0)).select_from(Expense)) or 0
    return {
        "users": {"total": total_users, "admins": total_admins, "travelers": total_users - total_admins},
        "stories": {"total": total_stories, "approved": approved_stories, "pending": pending_stories},
        "trips": {"total": total_trips},
        "expenses": {"records": total_expenses, "amount": float(total_expense_amount)},
        "knowledge": {
            "gemini_configured": ai_is_configured(),
            "ai_packages_available": ai_dependencies_available(),
            "community_index_state_exists": COMMUNITY_STATE_FILE.exists(),
        },
        "generated_at": datetime.utcnow(),
    }


@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.scalars(select(User).order_by(User.created_at.desc(), User.id.desc())).all()
    return [_user_dict(user) for user in users]


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    """Permanently delete a user and the records owned by that user."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own administrator account")

    if user.role == "admin":
        admin_count = db.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        ) or 0
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="You cannot delete the last administrator account")

    # Remove dependent records first because trips have a non-null user foreign key.
    # Stories are removed rather than left attached to a deleted account.
    db.query(Trip).filter(Trip.user_id == user.id).delete(synchronize_session=False)
    db.query(Expense).filter(Expense.user_id == user.id).delete(synchronize_session=False)
    db.query(Story).filter(Story.user_id == user.id).delete(synchronize_session=False)
    db.delete(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="User could not be deleted because of a database error")

    return {
        "message": "User and associated trips, expenses, and stories deleted successfully",
        "id": user_id,
    }


@router.patch("/users/{user_id}/role")
def update_user_role(user_id: int, role: str, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    if role not in {"traveler", "admin"}:
        raise HTTPException(status_code=400, detail="Role must be traveler or admin")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and role != "admin":
        raise HTTPException(status_code=400, detail="You cannot remove your own administrator role")
    user.role = role
    db.commit()
    db.refresh(user)
    return _user_dict(user)


@router.get("/stories")
def list_all_stories(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    stories = db.scalars(select(Story).order_by(Story.created_at.desc(), Story.id.desc())).all()
    return [_story_dict(story) for story in stories]


@router.patch("/stories/{story_id}/approval")
def set_story_approval(story_id: int, approved: bool, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    story.approved = approved
    db.commit()
    db.refresh(story)
    return _story_dict(story)


@router.delete("/stories/{story_id}")
def delete_story(story_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="Story not found")
    db.delete(story)
    db.commit()
    return {"message": "Story deleted successfully", "id": story_id}
