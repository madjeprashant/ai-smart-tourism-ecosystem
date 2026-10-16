from fastapi import APIRouter

router = APIRouter(
    prefix="/api",
    tags=["Food"]
)


@router.get("/foods")
def food(destination: str = "Bengaluru"):

    return [
        {
            "name": "Farm-to-table Restaurant",
            "type": "Dinner"
        },
        {
            "name": "Street Food",
            "type": "Snack"
        }
    ]