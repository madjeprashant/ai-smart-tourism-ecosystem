"""
One-time safe bootstrap for the first administrator.

Normal registration always creates a traveler. This command promotes an
existing user to administrator only when the database currently has no admin.
It never accepts or stores a password and it cannot replace an existing admin.

Usage:
    python scripts/bootstrap_admin.py --email user@example.com
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.crud import get_user_by_email
from app.database import SessionLocal
from app.models import User


def bootstrap_admin(db, email: str):
    """Promote an existing user only when no administrator exists yet."""
    email = email.strip()
    if not email:
        raise ValueError("Email is required")

    existing_admin = db.query(User).filter(User.role == "admin").first()
    if existing_admin is not None:
        raise RuntimeError("An administrator already exists; bootstrap is disabled")

    user = get_user_by_email(db, email)
    if user is None:
        raise LookupError("No registered user exists with that email")

    user.role = "admin"
    db.commit()
    db.refresh(user)
    return user


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the first VoyageAI administrator")
    parser.add_argument("--email", required=True, help="Email of an existing registered user")
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            user = bootstrap_admin(db, args.email)
        except (ValueError, RuntimeError, LookupError) as exc:
            print(f"ERROR: {exc}")
            return 1

    print(f"SUCCESS: {user.email} is now an administrator.")
    print("For security, bootstrap is available only while no administrator exists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
