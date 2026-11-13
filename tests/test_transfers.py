"""UI-4 Transfer risk acceptance tests.

Acceptance criteria: given two routes and a stop, the system shows the % of
past trips where the transfer would have been made.
"""
from datetime import date

import pytest

from app import timeutil, transfers
from app.api import create_app
from app.simulate import seed_history

from .conftest import NOW

WED = date(2026, 10, 28)
SAT = date(2026, 10, 31)
STOP = "UNIV_KING"
A_HEAD, B_HEAD = "Fairway Station", "Conestoga"   # Route 7 southbound, Route 201 to Conestoga


def hm(h, m=0):
    return h * 3600 + m * 60


def add(conn, trip_id, route_id, service_date, secs, delay, cancelled=False):
    sched = timeutil.scheduled_datetime(service_date, secs)
    conn.execute(
        """INSERT INTO trip_updates (trip_id, stop_id, route_id, service_date, service_dow,
               scheduled_secs, scheduled_arrival, predicted_arrival, delay_seconds, cancelled, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, STOP, route_id, service_date.isoformat(), service_date.weekday(), secs,
         sched.isoformat(), None, None if cancelled else delay, int(cancelled), sched.isoformat()))


def trip_ids(conn, route_id, headsign, n):
    return [r["trip_id"] for r in conn.execute(
        "SELECT trip_id FROM trips WHERE route_id = ? AND headsign = ? ORDER BY trip_id LIMIT ?",
        (route_id, headsign, n))]


@pytest.fixture
def history(conn):
    """Hand-made arrivals with known answers (buffer 2 minutes):

    A1 Wed 8:00 on time   -> planned B1 8:05 on time          -> MADE
    A2 Wed 9:00 6 min late-> planned B2 9:05 on time          -> MISSED (next: B3 9:20, 15 min extra)
    A3 Wed 10:00 on time  -> planned B4 10:05 CANCELLED       -> MISSED (next: B5 10:20 +1 min, 16 min extra)
    A4 Wed 11:00 CANCELLED                                     -> skipped, counted in cancelled_arrivals
    A5 Sat 8:00 on time   -> planned B6 8:05 on time          -> MADE
    """
    conn.execute("UPDATE trips SET wheelchair_accessible = 1")
    a, b = trip_ids(conn, "7", A_HEAD, 5), trip_ids(conn, "201", B_HEAD, 6)
    add(conn, a[0], "7", WED, hm(8), 0)
    add(conn, b[0], "201", WED, hm(8, 5), 0)
    add(conn, a[1], "7", WED, hm(9), 360)
    add(conn, b[1], "201", WED, hm(9, 5), 0)
    add(conn, b[2], "201", WED, hm(9, 20), 0)
    add(conn, a[2], "7", WED, hm(10), 0)
    add(conn, b[3], "201", WED, hm(10, 5), None, cancelled=True)
    add(conn, b[4], "201", WED, hm(10, 20), 60)
    add(conn, a[3], "7", WED, hm(11), None, cancelled=True)
    add(conn, a[4], "7", SAT, hm(8), 0)
    add(conn, b[5], "201", SAT, hm(8, 5), 0)
    conn.commit()
    return conn


def risk(conn, **kw):
    return transfers.transfer_risk(conn, STOP, "7", "201", from_headsign=A_HEAD, to_headsign=B_HEAD, **kw)


# ---------- The calculation ----------

def test_made_and_missed_transfers(history):
    r = risk(history)
    assert (r["made"], r["missed"], r["connections"]) == (2, 2, 4)
    assert r["made_pct"] == 50
    assert r["cancelled_arrivals"] == 1


def test_wait_and_gap(history):
    r = risk(history)
    assert r["avg_planned_gap_min"] == 5.0
    assert r["avg_extra_wait_min"] == 15.5


def test_small_samples_are_flagged(history):
    r = risk(history)
    assert r["limited_data"] is True
    assert r["verdict"] == "Not enough data"
    assert r["advice"]


def test_day_filter(history):
    r = risk(history, day="weekday")
    assert (r["made"], r["connections"], r["made_pct"]) == (1, 3, 33)
    assert r["filters"] == {"day": "weekday", "time": "all"}


def test_time_filter(history):
    r = risk(history, time_of_day="am_peak")  # 7-10 AM: A1, A2, A5
    assert (r["made"], r["missed"]) == (2, 1)


def test_larger_buffer_changes_the_planned_bus(history):
    # Needing 6 minutes, A1 (8:00) plans on B2 at 9:05 instead of B1 at 8:05.
    r = risk(history, buffer_min=6, day="weekday", time_of_day="am_peak")
    assert r["avg_planned_gap_min"] > 5.0


def test_accessible_filter_applies_to_both_legs(history):
    history.execute("UPDATE trips SET wheelchair_accessible = 2 WHERE trip_id = ?", (trip_ids(history, "7", A_HEAD, 1)[0],))
    history.commit()
    r = risk(history, accessible_only=True)
    assert r["connections"] == 3
    assert r["accessible_only"] is True


def test_any_direction_when_headsign_is_left_out(history):
    r = transfers.transfer_risk(history, STOP, "7", "201")
    assert r["connections"] == 4


@pytest.mark.parametrize("pct,expected", [
    (100, "Very likely"), (90, "Very likely"), (89, "Likely"), (75, "Likely"),
    (74, "Risky"), (50, "Risky"), (49, "Unlikely"), (0, "Unlikely"), (None, "Not enough data"),
])
def test_verdicts(pct, expected):
    assert transfers.verdict(pct) == expected


def test_real_history_gives_a_verdict(conn):
    seed_history(conn, days=7, today=NOW.date())
    r = risk(conn)
    assert r["connections"] >= 10
    assert 0 <= r["made_pct"] <= 100
    assert r["verdict"] in {"Very likely", "Likely", "Risky", "Unlikely"}


# ---------- Options and errors ----------

def test_transfer_options(conn):
    opts = transfers.transfer_options(conn, STOP)
    assert "7 to Fairway Station" in {o["label"] for o in opts["arrive"]}
    assert "201 to Conestoga" in {o["label"] for o in opts["leave"]}
    assert {"route_id", "route", "headsign", "label"} <= set(opts["arrive"][0])


def test_cannot_arrive_on_a_trip_that_starts_here_or_leave_on_one_that_ends_here(conn):
    opts = transfers.transfer_options(conn, "CONESTOGA")  # Route 7 starts and ends here
    assert "7 to Fairway Station" not in {o["label"] for o in opts["arrive"]}
    assert "7 to Conestoga Station" not in {o["label"] for o in opts["leave"]}


@pytest.mark.parametrize("kw", [
    {"to_route": "201", "buffer_min": 16},
    {"to_route": "201", "buffer_min": -1},
    {"to_route": "7", "to_headsign": A_HEAD},   # same route and direction
    {"to_route": "9"},                          # Route 9 does not serve this stop
])
def test_invalid_requests_raise(history, kw):
    to_route = kw.pop("to_route")
    with pytest.raises(ValueError):
        transfers.transfer_risk(history, STOP, "7", to_route, from_headsign=A_HEAD, **kw)


# ---------- API ----------

@pytest.fixture
def client(history, db_path):
    return create_app(db_path=db_path, now_fn=lambda: NOW).test_client()


def test_options_endpoint(client):
    data = client.get(f"/api/stops/{STOP}/transfer-options").get_json()
    assert data["arrive"] and data["leave"]


def test_transfer_endpoint(client):
    res = client.get(f"/api/stops/{STOP}/transfer?from=7&from_headsign={A_HEAD}&to=201"
                     f"&to_headsign={B_HEAD}&buffer=2&day=all&time=all")
    assert res.status_code == 200
    assert res.get_json()["made_pct"] == 50


def test_transfer_endpoint_errors(client):
    assert client.get("/api/stops/NOPE/transfer?from=7&to=201").status_code == 404
    assert client.get("/api/stops/NOPE/transfer-options").status_code == 404
    assert client.get(f"/api/stops/{STOP}/transfer?from=7").status_code == 400
    assert client.get(f"/api/stops/{STOP}/transfer?from=7&to=201&buffer=abc").status_code == 400
    bad = client.get(f"/api/stops/{STOP}/transfer?from=7&to=9")
    assert bad.status_code == 400 and bad.get_json()["error"]
