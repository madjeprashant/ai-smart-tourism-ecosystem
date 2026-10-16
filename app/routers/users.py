from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..crud import create_user, get_user_by_email, get_user_by_username
from ..database import get_db
from ..schemas import UserRegister
from ..auth import verify_password, create_access_token
from ..models import User

router = APIRouter(
    prefix="/api",
    tags=["Users"],
)


@router.post("/register")
def register(user: UserRegister, db: Session = Depends(get_db)):
    if get_user_by_email(db, str(user.email)):
        raise HTTPException(status_code=400, detail="Email already registered")

    if get_user_by_username(db, user.username):
        raise HTTPException(status_code=400, detail="Username already registered")

    create_user(db, user)

    return {"message": "Registration Successful"}


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    identifier = form_data.username.strip()

    db_user = (
        db.query(User)
        .filter(or_(User.email == identifier, User.username == identifier))
        .first()
    )

    if not db_user or not verify_password(form_data.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid username/email or password")

    access_token = create_access_token({"sub": db_user.email})

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
