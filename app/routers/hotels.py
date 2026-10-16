from fastapi import APIRouter,Query
from ..services.hotels_service import get_hotels
router=APIRouter(prefix="/api",tags=["Hotels"])
@router.get("/hotels")
def hotels(destination:str=Query(default="Bengaluru",min_length=2,max_length=120)): return get_hotels(destination.strip())
