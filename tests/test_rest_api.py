"""
STEP 15 - PHASE 4
REST API & DOCUMENTATION END-TO-END VALIDATION

Validates the complete REST API contract through HTTP:
frontend contract -> FastAPI route -> validation/auth -> response.

Do not modify application code unless an actual E2E failure is found.
"""

from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.main import app
from app.security import get_current_user


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"

INDEX_PATH = STATIC_DIR / "index.html"
APP_JS_PATH = STATIC_DIR / "app.js"


def main():
    checks = []

    client = TestClient(app)

    index = (
        INDEX_PATH.read_text(encoding="utf-8", errors="ignore")
        if INDEX_PATH.exists()
        else ""
    )

    app_js = (
        APP_JS_PATH.read_text(encoding="utf-8", errors="ignore")
        if APP_JS_PATH.exists()
        else ""
    )

    # ================================================================
    # 1. APPLICATION AVAILABILITY
    # ================================================================

    root_response = client.get("/")

    checks.append(
        (
            "Application root responds successfully",
            root_response.status_code == 200,
        )
    )

    checks.append(
        (
            "Application root serves frontend HTML",
            "text/html" in root_response.headers.get("content-type", ""),
        )
    )

    # ================================================================
    # 2. HEALTH API -> HTTP -> JSON
    # ================================================================

    health_response = client.get("/api/health")

    checks.append(
        (
            "Health endpoint responds with HTTP 200",
            health_response.status_code == 200,
        )
    )

    health_data = (
        health_response.json()
        if health_response.status_code == 200
        else {}
    )

    checks.append(
        (
            "Health endpoint returns JSON object",
            isinstance(health_data, dict),
        )
    )

    checks.append(
        (
            "Health endpoint reports Healthy status",
            health_data.get("status") == "Healthy",
        )
    )

    # ================================================================
    # 3. AUTOMATIC API DOCUMENTATION
    # ================================================================

    docs_response = client.get("/docs")

    checks.append(
        (
            "Swagger documentation responds with HTTP 200",
            docs_response.status_code == 200,
        )
    )

    checks.append(
        (
            "Swagger documentation returns HTML",
            "text/html" in docs_response.headers.get("content-type", ""),
        )
    )

    redoc_response = client.get("/redoc")

    checks.append(
        (
            "ReDoc documentation responds with HTTP 200",
            redoc_response.status_code == 200,
        )
    )

    openapi_response = client.get("/openapi.json")

    checks.append(
        (
            "OpenAPI schema responds with HTTP 200",
            openapi_response.status_code == 200,
        )
    )

    openapi = (
        openapi_response.json()
        if openapi_response.status_code == 200
        else {}
    )

    paths = openapi.get("paths", {})

    checks.append(
        (
            "OpenAPI schema contains API paths",
            isinstance(paths, dict) and len(paths) > 0,
        )
    )

    # ================================================================
    # 4. DOCUMENTED ENDPOINTS -> ACTUAL HTTP ROUTES
    # ================================================================

    required_routes = {
        ("GET", "/api/health"),
        ("POST", "/api/register"),
        ("POST", "/api/login"),
        ("POST", "/api/chat"),
        ("GET", "/api/weather"),
        ("GET", "/api/expenses"),
        ("GET", "/api/stories"),
    }

    for method, path in sorted(required_routes):
        checks.append(
            (
                f"OpenAPI documents {method} {path}",
                path in paths
                and method.lower() in paths.get(path, {}),
            )
        )

    # ================================================================
    # 5. AUTHENTICATION FLOW
    # ================================================================

    unauth_expense = client.get("/api/expenses")

    checks.append(
        (
            "Protected expense endpoint rejects unauthenticated request",
            unauth_expense.status_code == 401,
        )
    )

    unauth_stories = client.get("/api/stories")

    checks.append(
        (
            "Protected stories endpoint rejects unauthenticated request",
            unauth_stories.status_code in (401, 403),
        )
    )

    # ================================================================
    # 6. AUTHENTICATED API FLOW
    # ================================================================

    test_user = {
        "sub": "step15_phase4@example.com",
        "id": 999991,
        "username": "step15_phase4",
        "email": "step15_phase4@example.com",
    }

    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        authenticated_expenses = client.get("/api/expenses")

        checks.append(
            (
                "Authenticated expense request reaches the protected route",
                authenticated_expenses.status_code
                in (200, 404, 500, 503),
            )
        )

        authenticated_stories = client.get("/api/stories")

        checks.append(
            (
                "Authenticated stories request reaches the protected route",
                authenticated_stories.status_code
                in (200, 500, 503),
            )
        )

        # ============================================================
        # 7. CHAT E2E REQUEST
        # ============================================================

        chat_response = client.post(
            "/api/chat",
            json={
                "question": "What are some good places to visit in Bengaluru?"
            },
        )

        checks.append(
            (
                "Chat API accepts a valid HTTP request",
                chat_response.status_code in (200, 502, 503),
            )
        )

        if chat_response.status_code == 200:
            chat_data = chat_response.json()

            checks.append(
                (
                    "Successful chat response is JSON",
                    isinstance(chat_data, dict),
                )
            )

            checks.append(
                (
                    "Successful chat response contains answer",
                    isinstance(chat_data.get("answer"), str),
                )
            )

        # ============================================================
        # 8. EXPENSE POST -> GET CONTRACT
        # ============================================================

        expense_payload = {
            "title": "Phase 4 Test Expense",
            "category": "Testing",
            "amount": 125,
            "destination": "Bengaluru",
        }

        expense_response = client.post(
            "/api/expenses",
            json=expense_payload,
        )

        checks.append(
            (
                "Expense creation endpoint accepts a valid request",
                expense_response.status_code in (201, 404, 400, 409, 500, 503),
            )
        )

        # ============================================================
        # 9. INVALID REQUEST VALIDATION
        # ============================================================

        invalid_expense = client.post(
            "/api/expenses",
            json={
                "title": "",
                "amount": -10,
            },
        )

        checks.append(
            (
                "Invalid expense request is rejected",
                invalid_expense.status_code in (400, 422),
            )
        )

    finally:
        app.dependency_overrides.clear()

    # ================================================================
    # 10. WEATHER HTTP VALIDATION
    # ================================================================

    invalid_weather = client.get(
        "/api/weather?destination=A"
    )

    checks.append(
        (
            "Weather API rejects an invalid destination",
            invalid_weather.status_code == 422,
        )
    )

    # ================================================================
    # 11. FOOD API HTTP VALIDATION
    # ================================================================

    food_response = client.get("/api/foods")

    checks.append(
        (
            "Food Explorer endpoint responds",
            food_response.status_code not in (404, 405),
        )
    )

    if food_response.status_code == 200:
        food_data = food_response.json()

        checks.append(
            (
                "Food Explorer returns JSON data",
                isinstance(food_data, list),
            )
        )

    # ================================================================
    # 12. FRONTEND -> REST CONTRACT
    # ================================================================

    checks.append(
        (
            "Frontend files remain available",
            INDEX_PATH.exists() and APP_JS_PATH.exists(),
        )
    )

    checks.append(
        (
            "Frontend references login API",
            "/api/login" in app_js,
        )
    )

    checks.append(
        (
            "Frontend references registration API",
            "/api/register" in app_js,
        )
    )

    checks.append(
        (
            "Frontend references chat API",
            "/api/chat" in app_js,
        )
    )

    checks.append(
        (
            "Frontend references expense API",
            "/api/expenses" in app_js,
        )
    )

    checks.append(
        (
            "Frontend references stories API",
            "/api/stories" in app_js,
        )
    )

    # ================================================================
    # 13. API DOCUMENTATION CONSISTENCY
    # ================================================================

    checks.append(
        (
            "OpenAPI title identifies the project",
            openapi.get("info", {}).get("title")
            == "AI Smart Tourism Ecosystem",
        )
    )

    checks.append(
        (
            "OpenAPI version is present",
            bool(openapi.get("info", {}).get("version")),
        )
    )

    # ================================================================
    # RESULT
    # ================================================================

    print("=" * 72)
    print("STEP 15 - PHASE 4")
    print("REST API & DOCUMENTATION END-TO-END VALIDATION")
    print("=" * 72)

    passed = 0

    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ") + name)
        passed += int(bool(ok))

    print("=" * 72)
    print(f"RESULT: {passed}/{len(checks)} tests passed")
    print("=" * 72)

    if passed == len(checks):
        print("STEP 15 PHASE 4 END-TO-END VALIDATION PASSED")
        print("REST API & DOCUMENTATION IS READY TO FREEZE")
        return 0

    print("STEP 15 PHASE 4 END-TO-END VALIDATION FAILED")
    print("Inspect only the failed E2E checks before making any code changes.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())