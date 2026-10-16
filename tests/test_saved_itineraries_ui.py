import inspect
from pathlib import Path

from app.main import app
from app.routers import itineraries

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"

def routes():
    return {(r.path, tuple(sorted(r.methods))) for r in app.routes if hasattr(r, "methods") and hasattr(r, "path")}

def main():
    checks = []
    routeset = routes()
    checks.append((
        "Saved itinerary API routes",
        (
            ("/api/itineraries", ("GET",)) in routeset
            and ("/api/itineraries", ("POST",)) in routeset
            and ("/api/itineraries/{trip_id}", ("GET",)) in routeset
            and ("/api/itineraries/{trip_id}", ("PUT",)) in routeset
            and ("/api/itineraries/{trip_id}", ("DELETE",)) in routeset
        ),
    ))
    html = (STATIC/"index.html").read_text(encoding="utf-8")
    js = (STATIC/"app.js").read_text(encoding="utf-8")
    css = (STATIC/"step8_saved_itineraries.css").read_text(encoding="utf-8")
    checks.append(("Saved trips section present", 'id="saved-itineraries-section"' in html and 'id="savedItineraries"' in html))
    checks.append(("Existing UI assets preserved", '/static/styles.css' in html and '/static/app.js' in html))
    checks.append(("Save action uses existing API", 'api("/api/itineraries"' in js and 'method: "POST"' in js))
    checks.append(("View and delete actions present", 'data-view-trip' in js and 'data-delete-trip' in js and '/api/itineraries/${id}' in js))
    checks.append(("Additive saved-trip CSS present", '.saved-itinerary-card' in css and '.saved-itineraries-grid' in css))
    source = inspect.getsource(itineraries)
    checks.append(("Existing user isolation retained", 'Trip.user_id == user.id' in source))
    print("="*65); print("PHASE 1 - STEP 8"); print("SAVED ITINERARIES UI VALIDATION"); print("="*65)
    passed=0
    for name, ok in checks:
        print(("PASS: " if ok else "FAIL: ")+name)
        passed += int(ok)
    print("="*65); print(f"RESULT: {passed}/{len(checks)} tests passed"); print("="*65)
    if passed == len(checks): print("STEP 8 PHASE 2 UI VALIDATION PASSED")
    else: print("STEP 8 PHASE 2 VALIDATION FAILED")
    print("No Gemini quota or external travel API is used by this test.")
if __name__ == "__main__": main()
