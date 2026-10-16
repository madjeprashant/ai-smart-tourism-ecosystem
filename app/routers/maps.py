from fastapi import APIRouter, HTTPException, Query

from ..services.maps_service import get_map_data
from ..services.routing_service import get_route


router = APIRouter(
    prefix="/api",
    tags=["Maps"],
)


@router.get("/maps")
def maps(
    destination: str = Query(
        default="Bengaluru",
        min_length=2,
        max_length=120,
        description="City or travel destination",
    )
):
    """Return map information for a destination."""
    destination = destination.strip()
    return get_map_data(destination)


@router.get("/route")
def route(
    start_lat: float = Query(..., ge=-90, le=90),
    start_lon: float = Query(..., ge=-180, le=180),
    end_lat: float = Query(..., ge=-90, le=90),
    end_lon: float = Query(..., ge=-180, le=180),
    mode: str = Query(
        default="drive",
        pattern="^(drive|walk|bicycle|scooter|truck)$",
    ),
):
    """Return a Geoapify route between two coordinates."""
    try:
        result = get_route(
            start_lat,
            start_lon,
            end_lat,
            end_lon,
            mode=mode,
        )
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Route provider is temporarily unavailable.",
        ) from error

    if result.get("status") == "quota_exhausted":
        raise HTTPException(
            status_code=429,
            detail="Geoapify routing daily application limit has been reached.",
        )

    return result
