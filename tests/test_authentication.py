"""
STEP 18 - PHASE 4
AUTHENTICATION & USER MANAGEMENT END-TO-END VALIDATION

Deterministic E2E validation:
- isolated in-memory SQLite database
- FastAPI TestClient
- no external services
- real registration/login/JWT/protected-route flow
- no application-code changes
"""

import importlib
import sys
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker


PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"PASS: {name}")
    else:
        FAIL_COUNT += 1
        print(f"FAIL: {name}")
        if detail:
            print(f"       {detail}")


def load_app():
    main = importlib.import_module("app.main")
    models = importlib.import_module("app.models")
    database = importlib.import_module("app.database")
    return main, models, database


@contextmanager
def isolated_app():
    main, models, database = load_app()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    models.Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    original_overrides = dict(main.app.dependency_overrides)
    main.app.dependency_overrides[database.get_db] = override_get_db

    try:
        yield main.app, models, TestingSessionLocal
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)
        engine.dispose()


def run():
    print("=" * 72)
    print("STEP 18 - PHASE 4")
    print("AUTHENTICATION & USER MANAGEMENT END-TO-END VALIDATION")
    print("=" * 72)

    with isolated_app() as (app, models, SessionLocal):
        client = TestClient(app)

        user_a = {
            "username": "e2e_traveler_a",
            "full_name": "E2E Traveler A",
            "email": "e2e.a@example.com",
            "phone": "9000000001",
            "password": "StrongPassword123!",
        }
        user_b = {
            "username": "e2e_traveler_b",
            "full_name": "E2E Traveler B",
            "email": "e2e.b@example.com",
            "phone": "9000000002",
            "password": "StrongPassword456!",
        }

        # ------------------------------------------------------------------
        # 1. Registration
        # ------------------------------------------------------------------
        register_a = client.post("/api/register", json=user_a)
        check(
            "User A registration succeeds",
            register_a.status_code == 200,
            f"HTTP {register_a.status_code}: {register_a.text}",
        )

        register_b = client.post("/api/register", json=user_b)
        check(
            "User B registration succeeds",
            register_b.status_code == 200,
            f"HTTP {register_b.status_code}: {register_b.text}",
        )

        check(
            "Registration response confirms success",
            register_a.status_code == 200
            and "message" in register_a.json(),
        )

        # ------------------------------------------------------------------
        # 2. Persistence + password storage
        # ------------------------------------------------------------------
        with SessionLocal() as db:
            db_a = (
                db.query(models.User)
                .filter(models.User.email == user_a["email"])
                .first()
            )
            db_b = (
                db.query(models.User)
                .filter(models.User.email == user_b["email"])
                .first()
            )

            check("User A persists in isolated database", db_a is not None)
            check("User B persists in isolated database", db_b is not None)

            if db_a:
                check(
                    "User A password is hashed",
                    db_a.password != user_a["password"],
                )
                check(
                    "User A default role is traveler",
                    db_a.role == "traveler",
                )
                check(
                    "User A username is persisted",
                    db_a.username == user_a["username"],
                )

            if db_b:
                check(
                    "User B password is hashed",
                    db_b.password != user_b["password"],
                )

        # ------------------------------------------------------------------
        # 3. Duplicate registration is rejected
        # ------------------------------------------------------------------
        duplicate = client.post("/api/register", json=user_a)
        check(
            "Duplicate email registration is rejected",
            duplicate.status_code == 400,
            f"HTTP {duplicate.status_code}: {duplicate.text}",
        )

        # ------------------------------------------------------------------
        # 4. Login by username
        # ------------------------------------------------------------------
        login_a_username = client.post(
            "/api/login",
            data={
                "username": user_a["username"],
                "password": user_a["password"],
            },
        )
        check(
            "User A can log in with username",
            login_a_username.status_code == 200,
            f"HTTP {login_a_username.status_code}: {login_a_username.text}",
        )

        token_a = login_a_username.json().get("access_token", "")
        check("Username login returns access token", bool(token_a))
        check(
            "Username login returns bearer token type",
            login_a_username.json().get("token_type") == "bearer",
        )

        # ------------------------------------------------------------------
        # 5. Login by email
        # ------------------------------------------------------------------
        login_a_email = client.post(
            "/api/login",
            data={
                "username": user_a["email"],
                "password": user_a["password"],
            },
        )
        check(
            "User A can log in with email",
            login_a_email.status_code == 200,
            f"HTTP {login_a_email.status_code}: {login_a_email.text}",
        )
        token_a_email = login_a_email.json().get("access_token", "")
        check("Email login returns access token", bool(token_a_email))

        login_b = client.post(
            "/api/login",
            data={
                "username": user_b["username"],
                "password": user_b["password"],
            },
        )
        check(
            "User B can log in with username",
            login_b.status_code == 200,
            f"HTTP {login_b.status_code}: {login_b.text}",
        )
        token_b = login_b.json().get("access_token", "")
        check("User B login returns access token", bool(token_b))

        # ------------------------------------------------------------------
        # 6. Invalid credentials
        # ------------------------------------------------------------------
        wrong_password = client.post(
            "/api/login",
            data={
                "username": user_a["username"],
                "password": "WrongPassword!",
            },
        )
        check(
            "Wrong password is rejected",
            wrong_password.status_code == 401,
            f"HTTP {wrong_password.status_code}: {wrong_password.text}",
        )

        unknown_user = client.post(
            "/api/login",
            data={
                "username": "does_not_exist@example.com",
                "password": "WrongPassword!",
            },
        )
        check(
            "Unknown user is rejected",
            unknown_user.status_code == 401,
            f"HTTP {unknown_user.status_code}: {unknown_user.text}",
        )

        # ------------------------------------------------------------------
        # 7. JWT + protected endpoint
        # Use an existing protected endpoint; chat is sufficient to prove
        # OAuth2 bearer authentication reaches application code.
        # ------------------------------------------------------------------
        protected_path = "/api/chat"

        no_token = client.post(
            protected_path,
            json={"message": "E2E authentication check"},
        )
        check(
            "Protected endpoint rejects missing token",
            no_token.status_code in (401, 403),
            f"HTTP {no_token.status_code}: {no_token.text}",
        )

        invalid_token = client.post(
            protected_path,
            headers={"Authorization": "Bearer definitely-invalid-token"},
            json={"message": "E2E authentication check"},
        )
        check(
            "Protected endpoint rejects invalid token",
            invalid_token.status_code == 401,
            f"HTTP {invalid_token.status_code}: {invalid_token.text}",
        )

        if token_a:
            protected_a = client.post(
                protected_path,
                headers={"Authorization": f"Bearer {token_a}"},
                json={"message": "E2E authentication check"},
            )
            check(
                "Valid User A token reaches protected endpoint",
                protected_a.status_code not in (401, 403),
                f"HTTP {protected_a.status_code}: {protected_a.text}",
            )

        if token_b:
            protected_b = client.post(
                protected_path,
                headers={"Authorization": f"Bearer {token_b}"},
                json={"message": "E2E authentication check"},
            )
            check(
                "Valid User B token reaches protected endpoint",
                protected_b.status_code not in (401, 403),
                f"HTTP {protected_b.status_code}: {protected_b.text}",
            )

        # ------------------------------------------------------------------
        # 8. Token identity + user isolation at the authentication layer
        # Decode through the project's actual verifier rather than guessing
        # JWT internals.
        # ------------------------------------------------------------------
        auth = importlib.import_module("app.auth")

        payload_a = auth.verify_token(token_a) if token_a else None
        payload_b = auth.verify_token(token_b) if token_b else None

        check("User A token verifies successfully", payload_a is not None)
        check("User B token verifies successfully", payload_b is not None)

        if payload_a:
            check(
                "User A token identifies User A",
                payload_a.get("sub") == user_a["email"],
                f"sub={payload_a.get('sub')!r}",
            )

        if payload_b:
            check(
                "User B token identifies User B",
                payload_b.get("sub") == user_b["email"],
                f"sub={payload_b.get('sub')!r}",
            )

        check(
            "User A and User B receive distinct tokens",
            bool(token_a and token_b and token_a != token_b),
        )

        # ------------------------------------------------------------------
        # 9. Expiration contract
        # ------------------------------------------------------------------
        if payload_a:
            check("User A JWT contains expiration", "exp" in payload_a)

        # ------------------------------------------------------------------
        # 10. Authenticated application state remains isolated
        # ------------------------------------------------------------------
        with SessionLocal() as db:
            count = db.query(models.User).count()
            check(
                "Isolated E2E database contains exactly two users",
                count == 2,
                f"user_count={count}",
            )

            emails = {
                row.email
                for row in db.query(models.User).all()
            }
            check(
                "User A and User B records remain distinct",
                emails == {user_a["email"], user_b["email"]},
                f"emails={emails}",
            )

    print("=" * 72)
    print(f"RESULT: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} tests passed")
    print("=" * 72)

    if FAIL_COUNT:
        print("STEP 18 PHASE 4 END-TO-END VALIDATION FAILED")
        print("Fix only proven E2E defects before freezing.")
        return 1

    print("STEP 18 PHASE 4 END-TO-END VALIDATION PASSED")
    print("AUTHENTICATION & USER MANAGEMENT IS READY TO FREEZE")
    return 0


if __name__ == "__main__":
    sys.exit(run())
