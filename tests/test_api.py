"""API tests for UI-2 (map), UI-3 (live arrivals and alerts) and UI-1 (history)."""
from datetime import timedelta

import pytest

from app.api import create_app
from app.collector import SampleFeedSource, collect_once
from app.simulate import seed_history

from .conftest import NOW


@pytest.fixture
def client(conn, db_path):
    seed_history(conn, days=7, today=NOW.date())
    collect_once(conn, SampleFeedSource(), NOW)
    app = create_app(db_path=db_path, now_fn=lambda: NOW)
    return app.test_client()


def test_stops_list_for_map(client):
    data = client.get("/api/stops").get_json()
    assert len(data["stops"]) == 11
    first = data["stops"][0]
    assert {"stop_id", "stop_name", "lat", "lon", "accessible", "routes", "distance_m"} <= set(first)
    distances = [s["distance_m"] for s in data["stops"]]
    assert distances == sorted(distances)


def test_accessible_filter_and_search(client):
    accessible = client.get("/api/stops?accessible=1").get_json()["stops"]
    assert all(s["accessible"] for s in accessible)
    assert "ALBERT_SEAGRAM" not in {s["stop_id"] for s in accessible}
    by_route = client.get("/api/stops?q=9").get_json()["stops"]
    assert {s["stop_id"] for s in by_route} == {"PUBLIC_SQUARE", "ALBERT_SEAGRAM", "PHILLIP_COLUMBIA"}
    by_name = client.get("/api/stops?q=fairway").get_json()["stops"]
    assert [s["stop_id"] for s in by_name] == ["FAIRWAY"]


def test_stop_detail_includes_alerts(client):
    data = client.get("/api/stops/UNIV_KING").get_json()
    assert data["accessible"] is True
    assert {r["short_name"] for r in data["routes"]} == {"7", "201"}
    assert any("detour" in a["header"].lower() for a in data["alerts"])


def test_live_arrivals(client):
    data = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    assert data["live"] is True
    assert 0 < len(data["arrivals"]) <= 6
    for a in data["arrivals"]:
        assert a["label"]  # every arrival has a text status
    assert any(a["is_live"] for a in data["arrivals"])


def test_stale_feed_shows_schedule_with_notice(conn, db_path):
    collect_once(conn, SampleFeedSource(), NOW)
    later = NOW + timedelta(minutes=10)  # no collection for 10 minutes
    client = create_app(db_path=db_path, now_fn=lambda: later).test_client()
    data = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    assert data["live"] is False
    assert "unavailable" in data["notice"]
    assert all(a["label"] == "Scheduled" for a in data["arrivals"])


def test_reliability_endpoint_with_filters(client):
    data = client.get("/api/stops/UNIV_KING/reliability?day=weekday&time=pm_peak").get_json()
    assert data["filters"] == {"day": "weekday", "time": "pm_peak"}
    assert data["overall"]["trips"] > 0
    assert 0 <= data["overall"]["on_time_pct"] <= 100


def test_bad_requests(client):
    assert client.get("/api/stops/NOPE").status_code == 404
    assert client.get("/api/stops/UNIV_KING/reliability?day=funday").status_code == 400
    assert client.get("/api/routes/NOPE/reliability").status_code == 404


def test_status_reports_collection_success_rate(client):
    data = client.get("/api/status").get_json()
    assert data["live"] is True
    assert data["success_rate_24h"] == 100.0
