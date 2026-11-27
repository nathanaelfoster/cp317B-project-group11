"""REP-4a Analyst reports acceptance tests.

Acceptance criteria (backlog): an analyst can view the least reliable accessible
routes, the stops with the most barrier reports, and average resolution time.
Only analysts and admins can see them.
"""
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import analyst, timeutil
from app.api import create_app

from .conftest import NOW

WED, SAT = date(2026, 10, 28), date(2026, 10, 24)
OLD = WED - timedelta(days=40)


def hm(h, m=0):
    return h * 3600 + m * 60


def trip_ids(conn, route_id, n):
    return [r["trip_id"] for r in conn.execute(
        "SELECT trip_id FROM trips WHERE route_id = ? ORDER BY trip_id LIMIT ?", (route_id, n))]


def add(conn, trip_id, route_id, service_date, secs, delay, cancelled=False, stop="UNIV_KING"):
    sched = timeutil.scheduled_datetime(service_date, secs)
    conn.execute(
        """INSERT INTO trip_updates (trip_id, stop_id, route_id, service_date, service_dow,
               scheduled_secs, scheduled_arrival, predicted_arrival, delay_seconds, cancelled, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, stop, route_id, service_date.isoformat(), service_date.weekday(), secs,
         sched.isoformat(), None, None if cancelled else delay, int(cancelled), sched.isoformat()))


@pytest.fixture
def history(conn):
    """Hand-made arrivals with known answers (NOW is Wednesday Oct 28, min_trips 3):

    Route 7, accessible, Wed 8 AM:  0, +400, +600, -200 s and 1 cancelled
        -> 4 trips, 1 on time = 25%, avg 200 s = 3.3 min, cancelled 1
    Route 7, NOT accessible, Wed:   +900 s            -> left out
    Route 201, accessible, 5 PM:    Wed 0, +60, +120 s; Sat Oct 24 +400 s
        -> 4 trips, 3 on time = 75%, avg 145 s = 2.4 min
    Route 201, 40 days ago:         +900 s            -> outside 30 days, left out
    Route 9, accessible, Wed:       0, 0 s            -> only 2 trips, dropped by min_trips
    Order: 7 (25%), then 201 (75%).
    """
    conn.execute("UPDATE trips SET wheelchair_accessible = 1")
    r7, r201, r9 = trip_ids(conn, "7", 6), trip_ids(conn, "201", 5), trip_ids(conn, "9", 2)
    for trip, delay in zip(r7[:4], [0, 400, 600, -200]):
        add(conn, trip, "7", WED, hm(8), delay)
    add(conn, r7[4], "7", WED, hm(8), None, cancelled=True)
    conn.execute("UPDATE trips SET wheelchair_accessible = 2 WHERE trip_id = ?", (r7[5],))
    add(conn, r7[5], "7", WED, hm(8), 900)
    for trip, delay in zip(r201[:3], [0, 60, 120]):
        add(conn, trip, "201", WED, hm(17), delay)
    add(conn, r201[3], "201", SAT, hm(17), 400)
    add(conn, r201[4], "201", OLD, hm(17), 900)
    for trip in r9:
        add(conn, trip, "9", WED, hm(8), 0, stop="PUBLIC_SQUARE")
    conn.commit()
    return conn


def routes(conn, **kw):
    return analyst.least_reliable_accessible_routes(conn, NOW, min_trips=3, **kw)["routes"]


# ---------- Least reliable accessible routes ----------

def test_worst_accessible_route_first(history):
    r = routes(history)
    assert [x["route_id"] for x in r] == ["7", "201"]
    seven, two01 = r
    assert (seven["trips"], seven["on_time"], seven["on_time_pct"]) == (4, 1, 25)
    assert seven["avg_delay_min"] == 3.3
    assert seven["cancelled"] == 1
    assert (two01["trips"], two01["on_time_pct"], two01["avg_delay_min"]) == (4, 75, 2.4)


def test_inaccessible_trips_and_old_trips_are_left_out(history):
    seven = routes(history)[0]
    assert seven["trips"] == 4          # the +900 s inaccessible trip isn't counted
    two01 = routes(history)[1]
    assert two01["trips"] == 4          # the trip 40 days ago isn't counted
    assert routes(history, days=60)[1]["trips"] == 5


def test_routes_under_min_trips_are_dropped(history):
    assert "9" not in {x["route_id"] for x in routes(history)}
    everything = analyst.least_reliable_accessible_routes(history, NOW, min_trips=2)["routes"]
    assert "9" in {x["route_id"] for x in everything}


def test_day_and_time_filters(history):
    weekday = {x["route_id"]: x for x in routes(history, dow="weekday")}
    assert weekday["201"]["on_time_pct"] == 100    # the Saturday +400 s is filtered out
    assert [x["route_id"] for x in routes(history, time="am_peak")] == ["7"]


def test_limit(history):
    assert len(routes(history, limit=1)) == 1


# ---------- Barrier reports ----------

def add_user(conn, username, role):
    # pbkdf2 works on every Python build (some lack hashlib.scrypt, werkzeug's default),
    # and a low round count keeps the tests quick. Never use this for real accounts.
    cur = conn.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                       (username, generate_password_hash("pw-12345678", method="pbkdf2:sha256:1000"), role,
                        NOW.isoformat()))
    return cur.lastrowid


def add_report(conn, user_id, stop, category, days_ago, status, resolve_after_h=None):
    created = NOW - timedelta(days=days_ago)
    resolved = created + timedelta(hours=resolve_after_h) if resolve_after_h is not None else None
    conn.execute(
        """INSERT INTO barrier_reports (stop_id, user_id, category, description, status,
               created_at, updated_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (stop, user_id, category, "test", status, created.isoformat(),
         (resolved or created).isoformat(), resolved.isoformat() if resolved else None))


@pytest.fixture
def reports(conn):
    """Hand-made reports with known answers:

    r1 UNIV_KING     ramp      2 days ago    open
    r2 UNIV_KING     ramp      10 days ago   resolved after 4 h
    r3 UNIV_KING     snow_ice  5 days ago    under review
    r4 FAIRWAY       shelter   20 days ago   resolved after 10 h
    r5 FAIRWAY       shelter   1 day ago     open
    r6 PUBLIC_SQUARE elevator  3 days ago    resolved after 48 h (1 day ago)
    r7 CONESTOGA     ramp      120 days ago  resolved after 24 h  -> outside 90 days everywhere
    r8 CONESTOGA     sidewalk  100 days ago  resolved after 480 h (80 days ago)
                                             -> not a hotspot (created too long ago),
                                                but counts for resolution time (resolved in window)

    Hotspots, 90 days: UNIV_KING 3 (1 open, 1 under review, 1 resolved, top ramp),
        FAIRWAY 2 (top shelter), PUBLIC_SQUARE 1 (elevator).
    Hotspots, 7 days: UNIV_KING 2 (r1, r3; ramp wins the 1-1 tie), then FAIRWAY 1
        (still open) before PUBLIC_SQUARE 1 (resolved).
    Resolution, 90 days: 4, 10, 48, 480 h -> avg 135.5, median 29.0, unresolved 3 (r1, r3, r5).
    Resolution, 7 days: only r6 -> avg 48.0, median 48.0, unresolved 3.
    """
    rider = add_user(conn, "rider_t", "rider")
    for args in [("UNIV_KING", "ramp", 2, "open"), ("UNIV_KING", "ramp", 10, "resolved", 4),
                 ("UNIV_KING", "snow_ice", 5, "under_review"), ("FAIRWAY", "shelter", 20, "resolved", 10),
                 ("FAIRWAY", "shelter", 1, "open"), ("PUBLIC_SQUARE", "elevator", 3, "resolved", 48),
                 ("CONESTOGA", "ramp", 120, "resolved", 24), ("CONESTOGA", "sidewalk", 100, "resolved", 480)]:
        add_report(conn, rider, *args)
    conn.commit()
    return conn


def test_report_hotspots(reports):
    stops = analyst.report_hotspots(reports, NOW)["stops"]
    assert [s["stop_id"] for s in stops] == ["UNIV_KING", "FAIRWAY", "PUBLIC_SQUARE"]
    univ = stops[0]
    assert (univ["total"], univ["open"], univ["under_review"], univ["resolved"]) == (3, 1, 1, 1)
    assert (univ["top_category"], univ["top_category_label"], univ["top_category_count"]) == \
        ("ramp", "Broken ramp", 2)
    assert stops[1]["top_category_label"] == "Damaged shelter"
    assert univ["stop_name"]


def test_report_hotspots_window_and_ties(reports):
    stops = analyst.report_hotspots(reports, NOW, days=7)["stops"]
    assert [(s["stop_id"], s["total"]) for s in stops] == [("UNIV_KING", 2), ("FAIRWAY", 1), ("PUBLIC_SQUARE", 1)]
    assert stops[0]["top_category"] == "ramp"
    assert len(analyst.report_hotspots(reports, NOW, limit=1)["stops"]) == 1


def test_resolution_time(reports):
    r = analyst.resolution_time(reports, NOW)
    assert (r["resolved"], r["avg_hours"], r["median_hours"], r["unresolved"]) == (4, 135.5, 29.0, 3)
    by = {c["category"]: c for c in r["by_category"]}
    assert [c["category"] for c in r["by_category"]] == ["ramp", "elevator", "sidewalk", "shelter"]
    assert (by["ramp"]["avg_hours"], by["sidewalk"]["median_hours"]) == (4.0, 480.0)
    assert by["shelter"]["label"] == "Damaged shelter"


def test_resolution_time_window(reports):
    r = analyst.resolution_time(reports, NOW, days=7)
    assert (r["resolved"], r["avg_hours"], r["median_hours"], r["unresolved"]) == (1, 48.0, 48.0, 3)


def test_nothing_resolved_gives_nulls(conn):
    r = analyst.resolution_time(conn, NOW)
    assert (r["resolved"], r["avg_hours"], r["median_hours"], r["unresolved"], r["by_category"]) == \
        (0, None, None, 0, [])
    assert analyst.report_hotspots(conn, NOW)["stops"] == []


# ---------- API: analysts and admins only ----------

@pytest.fixture
def client(history, reports, db_path):
    add_user(reports, "analyst_t", "analyst")
    add_user(reports, "admin_t", "admin")
    reports.commit()
    return create_app(db_path=db_path, now_fn=lambda: NOW).test_client()


def login(client, username):
    assert client.post("/api/auth/login", json={"username": username, "password": "pw-12345678"}).status_code == 200


ENDPOINTS = ["/api/analyst/accessible-routes", "/api/analyst/report-hotspots", "/api/analyst/resolution-time"]


@pytest.mark.parametrize("url", ENDPOINTS)
def test_logged_out_gets_401_and_rider_gets_403(client, url):
    assert client.get(url).status_code == 401
    login(client, "rider_t")
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("user", ["analyst_t", "admin_t"])
def test_analysts_and_admins_can_see_reports(client, user):
    login(client, user)
    routes_res = client.get("/api/analyst/accessible-routes?min_trips=3").get_json()
    assert [r["route_id"] for r in routes_res["routes"]] == ["7", "201"]
    assert client.get("/api/analyst/report-hotspots").get_json()["stops"][0]["stop_id"] == "UNIV_KING"
    assert client.get("/api/analyst/resolution-time").get_json()["median_hours"] == 29.0


@pytest.mark.parametrize("query", [
    "/api/analyst/accessible-routes?days=0",
    "/api/analyst/accessible-routes?days=366",
    "/api/analyst/accessible-routes?days=abc",
    "/api/analyst/accessible-routes?limit=51",
    "/api/analyst/accessible-routes?limit=0",
    "/api/analyst/accessible-routes?day=funday",
    "/api/analyst/accessible-routes?time=noonish",
    "/api/analyst/report-hotspots?days=400",
    "/api/analyst/report-hotspots?limit=99",
    "/api/analyst/resolution-time?days=-5",
])
def test_bad_query_values_get_400(client, query):
    login(client, "analyst_t")
    res = client.get(query)
    assert res.status_code == 400
    assert res.get_json()["error"]
