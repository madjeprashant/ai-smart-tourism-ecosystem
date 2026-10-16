"""
STEP 10 - PHASE 4
EXPENSE TRACKER END-TO-END VALIDATION

Purpose:
Validate the complete existing Expense Tracker flow using the real FastAPI
application, isolated test database, and the existing frontend contract.

Flow validated:
    Existing UI contract
        -> POST /api/expenses
        -> database persistence
        -> GET /api/expenses
        -> total/items response
        -> frontend rendering contract

The project's real database and external services are not used.

Run from the project root:
    python -m tests.test_expense_tracker_e2e_step10
"""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import Expense, User


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def find_current_user_dependency():
    """
    Find the exact get_current_user callable used by the existing expense
    routes, so this test does not assume a particular auth module layout.
    """
    for route in app.routes:
        if getattr(route, "path", None) not in {"/api/expenses"}:
            continue

        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue

        stack = list(getattr(dependant, "dependencies", []))

        while stack:
            dependency = stack.pop()
            call = getattr(dependency, "call", None)

            if getattr(call, "__name__", "") == "get_current_user":
                return call

            stack.extend(getattr(dependency, "dependencies", []))

    return None


def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_user():
    db = TestingSessionLocal()

    user = User(
        full_name="Expense E2E User",
        username="expense_e2e_user",
        email="expense_e2e@example.com",
        phone="9111111111",
        password="test-password",
        role="traveler",
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.close()

    return user_id, user.email


def read_static(filename):
    path = STATIC_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main():
    reset_database()
    user_id, user_email = seed_user()

    app.dependency_overrides[get_db] = override_get_db

    current_user_dependency = find_current_user_dependency()

    if current_user_dependency is not None:
        app.dependency_overrides[current_user_dependency] = (
            lambda: {"sub": user_email}
        )

    index_source = read_static("index.html")
    app_js_source = read_static("app.js")

    checks = []

    # ------------------------------------------------------------------
    # E2E starting point: existing UI
    # ------------------------------------------------------------------
    checks.append((
        "E2E starts from the existing expense form",
        'id="expenseForm"' in index_source
        and 'id="expenseTitle"' in index_source
        and 'id="expenseAmount"' in index_source,
    ))

    checks.append((
        "Existing UI submits to the real expense API endpoint",
        'api("/api/expenses"' in app_js_source
        and 'method: "POST"' in app_js_source,
    ))

    with TestClient(app) as client:

        # ------------------------------------------------------------------
        # UI submission -> POST API -> DB persistence
        # ------------------------------------------------------------------
        create_response = client.post(
            "/api/expenses",
            json={
                "title": "E2E Hotel",
                "category": "General",
                "amount": 1500,
                "destination": "Goa",
            },
        )

        checks.append((
            "UI submission flow reaches expense creation endpoint",
            create_response.status_code == 201,
        ))

        created = (
            create_response.json()
            if create_response.status_code == 201
            else {}
        )

        checks.append((
            "Created expense returns the submitted title",
            created.get("title") == "E2E Hotel",
        ))

        checks.append((
            "Created expense returns the submitted amount",
            created.get("amount") == 1500,
        ))

        checks.append((
            "Created expense returns the submitted destination",
            created.get("destination") == "Goa",
        ))

        # ------------------------------------------------------------------
        # API -> database
        # ------------------------------------------------------------------
        db = TestingSessionLocal()
        stored = db.execute(
            select(Expense).where(Expense.id == created.get("id"))
        ).scalar_one_or_none()

        checks.append((
            "Created expense is persisted in the database",
            stored is not None,
        ))

        checks.append((
            "Persisted expense belongs to the authenticated user",
            stored is not None
            and stored.user_id == user_id,
        ))

        checks.append((
            "Persisted expense retains the submitted values",
            stored is not None
            and stored.title == "E2E Hotel"
            and stored.amount == 1500
            and stored.destination == "Goa",
        ))

        db.close()

        # ------------------------------------------------------------------
        # DB -> GET API -> frontend list
        # ------------------------------------------------------------------
        list_response = client.get("/api/expenses")

        data = (
            list_response.json()
            if list_response.status_code == 200
            else {}
        )

        checks.append((
            "Expense list endpoint returns successfully",
            list_response.status_code == 200,
        ))

        checks.append((
            "GET response contains the persisted expense",
            any(
                item.get("id") == created.get("id")
                for item in data.get("items", [])
            ),
        ))

        checks.append((
            "GET response contains the correct total",
            data.get("total") == 1500,
        ))

        checks.append((
            "Existing frontend reads the expense list endpoint",
            'api("/api/expenses")' in app_js_source,
        ))

        checks.append((
            "Existing frontend renders the returned total",
            "data.total" in app_js_source
            and "Total spent:" in app_js_source,
        ))

        checks.append((
            "Existing frontend renders returned expense items",
            "data.items.map(item =>" in app_js_source
            and "escapeHtml(item.title)" in app_js_source
            and "money(item.amount)" in app_js_source,
        ))

        # ------------------------------------------------------------------
        # Second expense -> aggregation -> UI refresh contract
        # ------------------------------------------------------------------
        second_response = client.post(
            "/api/expenses",
            json={
                "title": "E2E Food",
                "category": "Food",
                "amount": 300,
                "destination": "Goa",
            },
        )

        checks.append((
            "Second UI submission also reaches the API",
            second_response.status_code == 201,
        ))

        second_list_response = client.get("/api/expenses")
        second_data = (
            second_list_response.json()
            if second_list_response.status_code == 200
            else {}
        )

        checks.append((
            "Expense total updates after the second submission",
            second_data.get("total") == 1800,
        ))

        checks.append((
            "Both persisted expenses are returned to the UI",
            len(second_data.get("items", [])) == 2,
        ))

        checks.append((
            "Existing frontend refreshes the list after submission",
            "event.currentTarget.reset();" in app_js_source
            and "loadExpenses();" in app_js_source,
        ))

    app.dependency_overrides.clear()

    print("=" * 72)
    print("STEP 10 - PHASE 4")
    print("EXPENSE TRACKER END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0

    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += int(bool(ok))

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    if passed == len(checks):
        print("STEP 10 PHASE 4 END-TO-END VALIDATION PASSED")
        print("EXPENSE TRACKER IS READY TO FREEZE")
        return 0

    print("STEP 10 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Fix only the failed E2E checks before freezing the Expense Tracker.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
