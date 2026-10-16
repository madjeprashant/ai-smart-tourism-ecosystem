from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models import Trip, User
from ..security import get_current_user


router = APIRouter(
    prefix="/api",
    tags=["Itineraries"]
)


@router.get("/itineraries")
def get_my_itineraries(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Get email from JWT
    user_email = current_user.get("sub")

    if not user_email:
        raise HTTPException(
            status_code=401,
            detail="Invalid user information in token"
        )

    # Find logged-in user
    user = db.scalar(
        select(User).where(User.email == user_email)
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Get ONLY this user's itineraries
    trips = db.scalars(
        select(Trip)
        .where(Trip.user_id == user.id)
        .order_by(Trip.created_at.desc())
    ).all()

    return {
        "message": "Your itineraries",
        "count": len(trips),
        "itineraries": [
            {
                "id": trip.id,
                "destination": trip.destination,
                "days": trip.days,
                "budget": trip.budget,
                "interests": trip.interests,
                "itinerary": trip.itinerary,
                "created_at": trip.created_at
            }
            for trip in trips
        ]
    }

# Get one itinerary belonging to the logged-in user
@router.get("/itineraries/{trip_id}")
def get_my_itinerary(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Get email from JWT
    user_email = current_user.get("sub")

    if not user_email:
        raise HTTPException(
            status_code=401,
            detail="Invalid user information in token"
        )

    # Find logged-in user
    user = db.scalar(
        select(User).where(User.email == user_email)
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Get the itinerary ONLY if it belongs to the logged-in user
    trip = db.scalar(
        select(Trip).where(
            Trip.id == trip_id,
            Trip.user_id == user.id
        )
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Itinerary not found"
        )

    return {
        "id": trip.id,
        "destination": trip.destination,
        "days": trip.days,
        "budget": trip.budget,
        "interests": trip.interests,
        "itinerary": trip.itinerary,
        "created_at": trip.created_at
    }

# Request body for updating an itinerary.
# Every field is optional so the user can update only what they want.
class ItineraryUpdate(BaseModel):
    destination: str | None = None
    days: int | None = None
    budget: float | None = None
    interests: dict | list | None = None
    itinerary: dict | list | None = None


@router.put("/itineraries/{trip_id}")
def update_my_itinerary(
    trip_id: int,
    data: ItineraryUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Get email from JWT
    user_email = current_user.get("sub")

    if not user_email:
        raise HTTPException(
            status_code=401,
            detail="Invalid user information in token"
        )

    # Find logged-in user
    user = db.scalar(
        select(User).where(User.email == user_email)
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # IMPORTANT:
    # Update ONLY an itinerary belonging to the logged-in user.
    trip = db.scalar(
        select(Trip).where(
            Trip.id == trip_id,
            Trip.user_id == user.id
        )
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Itinerary not found"
        )

    # Get only fields that were actually sent by the client.
    updates = data.model_dump(exclude_unset=True)

    # Basic validation
    if "destination" in updates and updates["destination"] is not None:
        if not updates["destination"].strip():
            raise HTTPException(
                status_code=400,
                detail="Destination cannot be empty"
            )

    if "days" in updates and updates["days"] is not None:
        if updates["days"] <= 0:
            raise HTTPException(
                status_code=400,
                detail="Days must be greater than 0"
            )

    if "budget" in updates and updates["budget"] is not None:
        if updates["budget"] < 0:
            raise HTTPException(
                status_code=400,
                detail="Budget cannot be negative"
            )

    # Apply the requested changes.
    for field, value in updates.items():
        setattr(trip, field, value)

    db.commit()
    db.refresh(trip)

    return {
        "message": "Itinerary updated successfully",
        "itinerary": {
            "id": trip.id,
            "destination": trip.destination,
            "days": trip.days,
            "budget": trip.budget,
            "interests": trip.interests,
            "itinerary": trip.itinerary,
            "created_at": trip.created_at
        }
    }

# Delete an itinerary belonging to the logged-in user
@router.delete("/itineraries/{trip_id}")
def delete_my_itinerary(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    # Get email from JWT
    user_email = current_user.get("sub")

    if not user_email:
        raise HTTPException(
            status_code=401,
            detail="Invalid user information in token"
        )

    # Find the logged-in user
    user = db.scalar(
        select(User).where(User.email == user_email)
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # Delete ONLY an itinerary belonging to the logged-in user.
    trip = db.scalar(
        select(Trip).where(
            Trip.id == trip_id,
            Trip.user_id == user.id
        )
    )

    if not trip:
        raise HTTPException(
            status_code=404,
            detail="Itinerary not found"
        )

    db.delete(trip)
    db.commit()

    return {
        "message": "Itinerary deleted successfully",
        "trip_id": trip_id
    }
