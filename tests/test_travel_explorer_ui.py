"""STEP 20 - PHASE 4
Frontend Travel Explorer UI integration contract tests.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_frontend_files_exist():
    assert (STATIC / "index.html").is_file()
    assert (STATIC / "app.js").is_file()
    assert (STATIC / "styles.css").is_file()


def test_travel_explorer_ui_contract():
    html = _read("index.html")
    assert 'href="#travel-explorer"' in html
    assert 'id="travel-explorer"' in html
    assert 'id="travelExplorerForm"' in html
    assert 'id="explorerDestination"' in html
    assert 'id="travelExplorerButton"' in html
    assert 'id="travelExplorerStatus"' in html
    assert 'id="travelExplorerResults"' in html
    assert "restaurants" in html.lower()
    assert "hotels" in html.lower()


def test_travel_explorer_uses_shared_api_helper_and_real_endpoints():
    js = _read("app.js")
    assert 'const api = async' in js
    assert 'api(`/api/maps?destination=${encodeURIComponent(destination)}`)' in js
    assert 'api(`/api/restaurants?destination=${encodeURIComponent(destination)}`)' in js
    assert 'api(`/api/hotels?destination=${encodeURIComponent(destination)}`)' in js


def test_travel_explorer_has_loading_success_and_error_states():
    js = _read("app.js")
    assert "Finding live travel information" in js
    assert 'className = "explorer-status loading"' in js
    assert 'className = "explorer-status success"' in js
    assert 'className = "explorer-status error"' in js
    assert "Promise.allSettled" in js
    assert "Other results are shown." in js


def test_travel_explorer_renders_provider_and_fallback_status():
    js = _read("app.js")
    assert "explorerProviderLabel" in js
    assert 'payload.status === "fallback"' in js
    assert 'payload.status === "no_data"' in js
    assert "Provider status:" in js


def test_travel_explorer_escapes_remote_values():
    js = _read("app.js")
    assert "escapeHtml(item.name" in js
    assert "escapeHtml(item.address" in js
    assert "escapeHtml(destination)" in js
    assert "encodeURIComponent(destination)" in js


def test_travel_explorer_does_not_expose_provider_keys():
    js = _read("app.js")
    # Configuration names may legitimately be mentioned in existing status/help text;
    # the security contract is that frontend code does not send provider credentials.
    assert "X-Goog-Api-Key" not in js
    assert "client_secret" not in js.lower()


def test_existing_trip_planner_contract_remains_intact():
    html = _read("index.html")
    js = _read("app.js")
    assert 'id="plannerForm"' in html
    assert 'id="destination"' in html
    assert 'id="days"' in html
    assert 'id="budget"' in html
    assert 'id="interests"' in html
    assert 'id="itinerary"' in html
    assert 'api("/api/itineraries/preview"' in js


def test_explorer_destination_layout_contract():
    js = _read("app.js")
    assert 'explorer-card explorer-card--destination' in js
    assert 'explorer-destination-name' in js
    assert 'explorer-destination-details' in js


def test_explorer_styles_are_present_and_responsive():
    css = _read("styles.css")
    for token in [
        ".travel-explorer-section",
        ".explorer-form",
        ".explorer-status",
        ".explorer-results",
        ".explorer-grid",
        ".explorer-card",
        ".explorer-error",
        ".explorer-card--destination",
        "scroll-margin-top",
        "scroll-padding-top:7rem",
        "@media (max-width: 900px)",
        "@media (max-width: 600px)",
    ]:
        assert token in css


def test_travel_explorer_hash_navigation_accounts_for_sticky_navbar():
    js = _read("app.js")
    assert 'a[href="#travel-explorer"]' in js
    assert 'event.preventDefault()' in js
    assert 'getBoundingClientRect().height' in js
    assert 'window.scrollTo({ top, behavior })' in js
    assert 'history.pushState(null, "", "#travel-explorer")' in js


def test_travel_explorer_navigation_items_are_separate():
    html = _read("index.html")
    assert '<li class="nav-item"><a class="nav-link" href="#travel-explorer">Travel Explorer</a></li>' in html
    assert '<li class="nav-item"><a class="nav-link" href="#tools">Travel tools</a></li>' in html


def test_travel_explorer_supports_area_destination_context():
    js = _read("app.js")
    assert "destination_context" in js
    assert "explorer-scope-badge" in js
    assert "isArea ? 7 : 12" in js
    assert "Area search" in js


def test_travel_explorer_resets_previous_route_when_destination_changes():
    js = _read("app.js")
    assert "const resetExplorerRouteState = () =>" in js
    assert "resetExplorerRouteState();" in js
    assert "explorerRouteOrigin = null;" in js
    assert "explorerLastRoute = null;" in js
    assert 'summary.classList.remove("is-visible")' in js


def test_travel_explorer_disables_routing_for_area_destinations():
    js = _read("app.js")
    assert "explorerDestinationContext" in js
    assert "Directions unavailable for area searches." in js
    assert "Use <em>View on map</em>" in js
    assert "explorerAreaNotice" in js
    assert "showExplorerAreaNotice" in js
    assert "if (explorerDestinationContext?.is_area)" in js


def test_travel_explorer_clears_route_state_when_routing_fails():
    js = _read("app.js")
    assert "clearExplorerRoute();" in js
    assert "hideExplorerRoutePanel();" in js
    assert "Directions unavailable." in js
    assert "You can still view this place on the map." in js


def test_travel_explorer_area_notice_stays_outside_map_overlay():
    html = _read("index.html")
    css = _read("styles.css")
    assert 'id="explorerAreaNotice"' in html
    assert ".explorer-area-notice" in css
    assert ".explorer-area-notice__content" in css
