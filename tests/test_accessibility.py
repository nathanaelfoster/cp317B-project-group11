"""UI-5 Accessibility filters acceptance tests.

Acceptance criteria: turning the filter on hides stops and trips not marked
wheelchair-accessible. "No information" (0) counts as not accessible.
"""
import pytest

from app import accessibility, reliability
from app.api import create_app
from app.collector import SampleFeedSource, collect_once
from app.simulate import seed_history

from .conftest import NOW


# ---------- Helpers in app/accessibility.py ----------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "on"])
def test_query_values_that_turn_the_filter_on(value):
    assert accessibility.wants_accessible(value) is True


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "maybe"])
def test_query_values_that_leave_the_filter_off(value):
    assert accessibility.wants_accessible(value) is False


def test_only_flag_1_is_accessible():
    assert accessibility.is_accessible(1) is True
    assert accessibility.is_accessible(2) is False
    assert accessibility.is_accessible(0) is False  # no information -> not accessible


def test_text_labels():
    assert accessibility.stop_label(1) == "Accessible stop"
    assert accessibility.stop_label(2) == "Not wheelchair accessible"
    assert accessibility.stop_label(0) == "Accessibility unknown"
    assert accessibility.stop_label(None) == "Accessibility unknown"
    assert accessibility.trip_label(1) == "Accessible bus"
    assert accessibility.trip_label(2) == "Not wheelchair accessible"


def test_trip_sql():
    assert accessibility.trip_sql("t") == "t.wheelchair_accessible = 1"


# ---------- Filter through the API ----------

@pytest.fixture
def marked(conn):
    """Known accessibility, whatever the sample data says: every Route 7 trip is an
    older bus, every other trip is accessible, Phillip St. / Columbia St. is unknown."""
    conn.execute("UPDATE trips SET wheelchair_accessible = CASE WHEN route_id = '7' THEN 2 ELSE 1 END")
    conn.execute("UPDATE stops SET wheelchair_boarding = 0 WHERE stop_id = 'PHILLIP_COLUMBIA'")
    conn.commit()
    seed_history(conn, days=7, today=NOW.date())
    collect_once(conn, SampleFeedSource(), NOW)
    return conn


@pytest.fixture
def client(marked, db_path):
    return create_app(db_path=db_path, now_fn=lambda: NOW).test_client()


def test_accessible_stops_hide_inaccessible_and_unknown(client):
    stops = client.get("/api/stops?accessible=1").get_json()["stops"]
    ids = {s["stop_id"] for s in stops}
    assert "ALBERT_SEAGRAM" not in ids     # marked not accessible
    assert "PHILLIP_COLUMBIA" not in ids   # no information
    assert all(s["accessible"] for s in stops)
    assert all(s["accessibility"] == "Accessible stop" for s in stops)


def test_stop_list_has_text_labels_when_filter_is_off(client):
    stops = {s["stop_id"]: s for s in client.get("/api/stops").get_json()["stops"]}
    assert len(stops) == 11
    assert stops["PHILLIP_COLUMBIA"]["accessibility"] == "Accessibility unknown"
    assert stops["ALBERT_SEAGRAM"]["accessibility"] == "Not wheelchair accessible"


def test_stop_detail_has_text_label(client):
    assert client.get("/api/stops/UNIV_KING").get_json()["accessibility"] == "Accessible stop"


def test_accessible_arrivals_hide_inaccessible_trips(client):
    everything = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    accessible = client.get("/api/stops/UNIV_KING/arrivals?accessible=1").get_json()
    assert any(a["route"] == "7" for a in everything["arrivals"])
    assert accessible["accessible_only"] is True
    assert accessible["arrivals"], "accessible Route 201 buses should still show"
    assert all(a["accessible"] for a in accessible["arrivals"])
    assert all(a["route"] != "7" for a in accessible["arrivals"])


def test_every_arrival_has_a_text_label(client):
    for a in client.get("/api/stops/UNIV_KING/arrivals").get_json()["arrivals"]:
        assert a["accessibility"] in ("Accessible bus", "Not wheelchair accessible")
        assert a["accessible"] == (a["accessibility"] == "Accessible bus")


def test_notice_when_the_stop_itself_is_not_accessible(client):
    data = client.get("/api/stops/ALBERT_SEAGRAM/arrivals?accessible=1").get_json()
    assert data["accessibility_notice"]
    assert "accessibility_notice" not in client.get("/api/stops/UNIV_KING/arrivals?accessible=1").get_json()


def test_accessible_reliability_counts_only_accessible_trips(client):
    everything = client.get("/api/stops/UNIV_KING/reliability").get_json()
    accessible = client.get("/api/stops/UNIV_KING/reliability?accessible=1").get_json()
    assert accessible["accessible_only"] is True
    assert {r["short_name"] for r in accessible["routes"]} == {"201"}
    assert 0 < accessible["overall"]["trips"] < everything["overall"]["trips"]


def test_route_reliability_with_filter(marked):
    assert reliability.route_reliability(marked, "7", accessible_only=True)["overall"]["trips"] == 0
    assert reliability.route_reliability(marked, "201", accessible_only=True)["overall"]["trips"] > 0


def test_filter_off_behaves_like_sprint_1(client):
    for url in ("/api/stops", "/api/stops/UNIV_KING/arrivals", "/api/stops/UNIV_KING/reliability"):
        off = client.get(f"{url}?accessible=0").get_json()
        default = client.get(url).get_json()
        off.pop("accessible_only", None), default.pop("accessible_only", None)
        off.pop("updated_at", None), default.pop("updated_at", None)
        assert off == default
