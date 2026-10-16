"""
PHASE 1 - STEP 8
SAVED ITINERARIES ARCHITECTURE VALIDATION - FIXED

This validates the EXISTING itinerary implementation.
It does not add a new router, model, table, or AI service.

Run:
    python -m tests.test_saved_itineraries_step8
"""

import inspect

from app.main import app
from app.routers import itineraries


def _http_routes():
    """Return only real HTTP routes; FastAPI also contains Mount routes."""
    return [
        route
        for route in app.routes
        if hasattr(route, "path")
        and hasattr(route, "methods")
    ]


def _route_signatures():
    return {
        (route.path, tuple(sorted(route.methods)))
        for route in _http_routes()
    }


def test_existing_routes_are_registered():
    routes = _route_signatures()

    assert ("/api/itineraries", ("GET",)) in routes
    assert ("/api/itineraries/{trip_id}", ("DELETE",)) in routes
    assert ("/api/itineraries/{trip_id}", ("GET",)) in routes
    assert ("/api/itineraries/{trip_id}", ("PUT",)) in routes


def test_existing_router_is_used():
    import app.main as main_module

    main_source = inspect.getsource(main_module)

    assert "itineraries_router" in main_source
    assert "app.include_router(itineraries_router)" in main_source


def test_user_isolation_is_present():
    source = inspect.getsource(itineraries)

    assert "Trip.user_id == user.id" in source
    assert "Trip.id == trip_id" in source


def test_authentication_guard_is_present():
    source = inspect.getsource(itineraries)

    assert "Depends(get_current_user)" in source
    assert "status_code=401" in source
    assert "Invalid user information in token" in source


def test_update_validation_is_present():
    source = inspect.getsource(itineraries)

    assert "model_dump(exclude_unset=True)" in source
    assert "Destination cannot be empty" in source
    assert "Days must be greater than 0" in source
    assert "Budget cannot be negative" in source


def test_existing_trip_model_is_reused():
    # Instead of depending on exact import formatting, verify that the
    # actual route functions use the existing SQLAlchemy Trip class.
    from app.models import Trip
    from app.models import User

    functions = (
        itineraries.get_my_itineraries,
        itineraries.get_my_itinerary,
        itineraries.update_my_itinerary,
    )

    for function in functions:
        globals_used = function.__globals__
        assert globals_used.get("Trip") is Trip
        assert globals_used.get("User") is User

    source = inspect.getsource(itineraries)
    assert "select(Trip)" in source


def main():
    tests = [
        ("Existing itinerary routes registered", test_existing_routes_are_registered),
        ("Existing router is used", test_existing_router_is_used),
        ("User isolation is present", test_user_isolation_is_present),
        ("Authentication guard is present", test_authentication_guard_is_present),
        ("Update validation is present", test_update_validation_is_present),
        ("Existing Trip model is reused", test_existing_trip_model_is_reused),
    ]

    print("=" * 65)
    print("PHASE 1 - STEP 8")
    print("SAVED ITINERARIES ARCHITECTURE VALIDATION")
    print("=" * 65)

    passed = 0

    for label, test in tests:
        try:
            test()
            print(f"PASS: {label}")
            passed += 1
        except Exception as exc:
            print(f"FAIL: {label}")
            print(f"ERROR: {exc}")

    print("=" * 65)
    print(f"RESULT: {passed}/{len(tests)} tests passed")
    print("=" * 65)

    if passed == len(tests):
        print("STEP 8 EXISTING ARCHITECTURE VALIDATION PASSED")
        print("No Gemini quota or external travel API is used by this test.")
        print("The existing itinerary router and Trip model are ready for the UI phase.")
    else:
        print("STEP 8 VALIDATION FAILED")
        print("Do not replace the itinerary architecture yet.")


if __name__ == "__main__":
    main()
