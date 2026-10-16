from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Expense, User
from ..schemas import ExpenseRequest
from ..security import get_current_user


router = APIRouter(
    prefix="/api",
    tags=["Expenses"]
)


@router.get("/expenses")
def list_expenses(
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

    # Get ONLY this user's expenses
    rows = db.scalars(
        select(Expense)
        .where(Expense.user_id == user.id)
        .order_by(Expense.created_at.desc())
    ).all()

    # Calculate ONLY this user's total
    total = db.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0))
        .where(Expense.user_id == user.id)
    )

    return {
        "total": total,
        "items": rows
    }


@router.post("/expenses", status_code=201)
def add_expense(
    payload: ExpenseRequest,
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

    # Create expense for THIS user
    expense = Expense(
        user_id=user.id,
        title=payload.title,
        category=payload.category,
        amount=payload.amount,
        destination=payload.destination
    )

    db.add(expense)
    db.commit()
    db.refresh(expense)

    return expense