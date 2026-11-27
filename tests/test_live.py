"""UI-3a Live arrivals with service alerts.

Acceptance criteria (backlog): given I pick a stop, when a bus is delayed, its
updated arrival time shows within 30 seconds of the live feed, with a status in
words, a detour flag, and how fresh the data is.
"""
from datetime import timedelta

import pytest

from app import live
from app.api import create_app
from app.collector import SampleFeedSource, collect_once
from app.simulate import seed_history

from .conftest import NOW


# ---------- Status for one arrival ----------

@pytest.mark.parametrize("delay, cancelled, has_prediction, expected", [
    (420, False, True, ("Late", "Late 7 min")),
    (-170, False, True, ("Early", "Early 3 min")),
    (-60, False, True, ("On time", "On time")),       # REP-1 edges stay on time
    (300, False, True, ("On time", "On time")),
    (301, False, True, ("Late", "Late 5 min")),
    (0, False, True, ("On time", "On time")),
    (None, True, False, ("Cancelled", "Cancelled")),
    (600, True, True, ("Cancelled", "Cancelled")),    # cancelled wins over a delay
    (None, False, False, ("Scheduled", "Scheduled")),
    (420, False, False, ("Scheduled", "Scheduled")),  # no live prediction: ignore the delay
    (None, False, True, ("Scheduled", "Scheduled")),
])
def test_arrival_status(delay, cancelled, has_prediction, expected):
    assert live.arrival_status(delay, cancelled, has_prediction) == expected


@pytest.mark.parametrize("effect, label", [
    ("DETOUR", "Detour"),
    ("REDUCED_SERVICE", "Reduced service"),
    ("NO_SERVICE", "No service"),
    ("SIGNIFICANT_DELAYS", "Significant delays"),
    ("STOP_MOVED", "Stop moved"),
    ("UNKNOWN_EFFECT", "Service change"),   # what GRT usually sends
    ("OTHER_EFFECT", "Service change"),
    (None, "Service change"),
])
def test_effect_labels(effect, label):
    assert live.effect_label(effect) == label


# ---------- Detours ----------

def add_alert(conn, alert_id, effect, entities, start=-2, end=6):
    """Alert active from `start` to `end` hours around NOW; entities are (route_id, stop_id)."""
    conn.execute(
        """INSERT INTO alerts (alert_id, header, effect, active_start, active_end, active, first_seen, last_seen)
           VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
        (alert_id, alert_id, effect, (NOW + timedelta(hours=start)).isoformat(),
         (NOW + timedelta(hours=end)).isoformat(), NOW.isoformat(), NOW.isoformat()))
    conn.executemany("INSERT INTO alert_entities (alert_id, route_id, stop_id) VALUES (?, ?, ?)",
                     [(alert_id, r, s) for r, s in entities])
    conn.commit()


def test_route_detour_flags_only_that_route(conn):
    # Like the sample alert: names Route 7 and the stop, so only the 7 is on detour.
    add_alert(conn, "d7", "DETOUR", [("7", None), (None, "UNIV_KING")])
    assert live.detoured_routes(conn, NOW, "UNIV_KING") == {"7"}


def test_stop_only_detour_flags_every_route_at_the_stop(conn):
    add_alert(conn, "stop", "DETOUR", [(None, "UNIV_KING")])
    assert live.detoured_routes(conn, NOW, "UNIV_KING") == {"7", "201"}


@pytest.mark.parametrize("effect, start, end, entities", [
    ("REDUCED_SERVICE", -2, 6, [("7", None)]),   # not a detour
    ("DETOUR", -5, -1, [("7", None)]),           # already over
    ("DETOUR", 1, 6, [("7", None)]),             # not started yet
    ("DETOUR", -2, 6, [("9", None)]),            # route doesn't serve this stop
    ("DETOUR", -2, 6, [(None, "FAIRWAY")]),      # a different stop
])
def test_alerts_that_are_not_a_detour_here(conn, effect, start, end, entities):
    add_alert(conn, "x", effect, entities, start, end)
    assert live.detoured_routes(conn, NOW, "UNIV_KING") == set()


# ---------- API ----------

@pytest.fixture
def client(conn, db_path):
    seed_history(conn, days=7, today=NOW.date())
    collect_once(conn, SampleFeedSource(), NOW)
    return create_app(db_path=db_path, now_fn=lambda: NOW + timedelta(seconds=12)).test_client()


def test_arrivals_have_status_detour_and_live(client):
    arrivals = client.get("/api/stops/UNIV_KING/arrivals").get_json()["arrivals"]
    assert arrivals
    for a in arrivals:
        assert a["status"] in {"Early", "On time", "Late", "Cancelled", "Scheduled"}
        assert a["status_label"] == a["label"]
        assert a["live"] == a["is_live"]
        assert a["detour"] == (a["route_id"] == "7")   # sample alert: Route 7 on detour
        assert {"accessible", "accessibility", "scheduled", "expected", "minutes_away"} <= set(a)
    assert any(a["live"] for a in arrivals)


def test_arrivals_say_how_fresh_the_data_is(client):
    data = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    assert data["feed_age_seconds"] == 12
    assert data["stale"] is False
    assert data["updated_at"].startswith(NOW.isoformat()[:19])


def test_stale_feed_is_flagged(conn, db_path):
    collect_once(conn, SampleFeedSource(), NOW)
    later = NOW + timedelta(minutes=10)
    client = create_app(db_path=db_path, now_fn=lambda: later).test_client()
    data = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    assert data["stale"] is True
    assert data["feed_age_seconds"] == 600
    assert all(a["status"] == "Scheduled" and not a["live"] for a in data["arrivals"]
               if a["status"] != "Cancelled")


def test_no_collection_yet(conn, db_path):
    client = create_app(db_path=db_path, now_fn=lambda: NOW).test_client()
    data = client.get("/api/stops/UNIV_KING/arrivals").get_json()
    assert data["stale"] is True
    assert data["feed_age_seconds"] is None
    assert data["updated_at"]


def test_alerts_have_effect_labels(client):
    alerts = client.get("/api/stops/UNIV_KING/arrivals").get_json()["alerts"]
    assert alerts and all(a["effect_label"] for a in alerts)
    assert {a["effect_label"] for a in alerts} == {"Detour"}
    detail = client.get("/api/stops/UNIV_KING").get_json()
    assert detail["alerts"][0]["effect_label"] == "Detour"
