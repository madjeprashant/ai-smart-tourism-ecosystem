from app.services import routing_service


def test_drive_route_falls_back_to_osrm_when_geoapify_quota_exhausted(monkeypatch):
    monkeypatch.setattr(routing_service.quota_manager, "can_consume", lambda provider: False)
    monkeypatch.setattr(
        routing_service, "_osrm_drive_route",
        lambda *args: {"type": "FeatureCollection", "features": [{"geometry": {"coordinates": [[1, 2], [3, 4]]}}], "provider": "OSRM", "fallback": True, "status": "fallback"},
    )
    result = routing_service.get_route(12.3, 76.6, 12.4, 76.7, mode="drive")
    assert result["provider"] == "OSRM"
    assert result["fallback"] is True


def test_non_driving_route_does_not_use_driving_fallback(monkeypatch):
    monkeypatch.setattr(routing_service.quota_manager, "can_consume", lambda provider: False)
    monkeypatch.setattr(routing_service, "_osrm_drive_route", lambda *args: (_ for _ in ()).throw(AssertionError("must not call OSRM")))
    try:
        routing_service.get_route(12.3, 76.6, 12.4, 76.7, mode="walk")
    except RuntimeError as exc:
        assert "no compatible fallback" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
