from fastapi import Depends, HTTPException
from .database import get_db
from fastapi.security import OAuth2PasswordBearer

from .auth import verify_token

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme)
):

    payload = verify_token(token)

    if payload is None:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    return payload

def get_current_admin(
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    """Require an authenticated user whose persisted role is admin."""
    from .crud import get_user_by_email

    user = get_user_by_email(db, current_user.get("sub", ""))
    if user is None:
        raise HTTPException(status_code=401, detail="Authenticated user not found")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user
