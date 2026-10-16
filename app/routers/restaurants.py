from fastapi import APIRouter,Query
from ..services.restaurants_service import get_restaurants
router=APIRouter(prefix="/api",tags=["Restaurants"])
@router.get("/restaurants")
def restaurants(destination:str=Query(default="Bengaluru",min_length=2,max_length=120)): return get_restaurants(destination.strip())
