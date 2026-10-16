from sqlalchemy.orm import Session

from .auth import hash_password
from .models import User
from .schemas import UserRegister


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def get_user_by_username(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, user: UserRegister):
    hashed = hash_password(user.password)

    db_user = User(
        username=user.username,
        full_name=user.full_name,
        email=str(user.email),
        phone=user.phone,
        password=hashed,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    return db_user
