"""UI-6a Part 2: submitting and listing barrier reports, with the rate limit."""
from datetime import timedelta

import pytest

from app import auth, barriers
from app.api import create_app

from .conftest import NOW

STOP = "UNIV_KING"
OTHER_STOPS = ["CONESTOGA", "COLUMBIA_KING", "UW_STATION", "LAURIER_PARK", "ALBERT_SEAGRAM",
               "PHILLIP_COLUMBIA", "PUBLIC_SQUARE", "GRAND_RIVER_HOSP", "KITCHENER_CITY_HALL", "FAIRWAY"]


class Clock:
    """A clock tests can move forward."""

    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def app(conn, db_path, clock):
    auth.seed_demo_users(conn)
    auth.create_user(conn, "sam", "password123")
    return create_app(db_path=db_path, now_fn=clock)


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username="rider_demo", password="demo-password"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    return res.get_json()["user"]


def submit(client, stop=STOP, category="ramp", description="Ramp is cracked and blocked by snow"):
    return client.post(f"/api/stops/{stop}/reports", json={"category": category, "description": description})


def test_logged_out_submit_returns_401(client, conn):
    res = submit(client)
    assert res.status_code == 401
    assert conn.execute("SELECT COUNT(*) FROM barrier_reports").fetchone()[0] == 0


def test_unknown_stop_returns_404(client):
    login(client)
    assert submit(client, stop="NOPE").status_code == 404
    assert client.get("/api/stops/NOPE/reports").status_code == 404


@pytest.mark.parametrize("category,description", [
    ("lava", "Something odd"),
    (None, "Something odd"),
    ("ramp", ""),
    ("ramp", "   "),
    ("ramp", None),
    ("ramp", "x" * 501),
])
def test_bad_category_or_description_returns_400(client, category, description):
    login(client)
    res = submit(client, category=category, description=description)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_500_character_description_is_allowed(client):
    login(client)
    assert submit(client, description="x" * 500).status_code == 201


def test_new_report_is_open_with_one_history_row(client, conn):
    user = login(client)
    res = submit(client, category="snow_ice", description="  Snowbank over the pad  ")
    assert res.status_code == 201
    report = res.get_json()
    assert report == {
        "id": report["id"],
        "stop_id": STOP,
        "stop_name": "University Ave. / King St.",
        "category": "snow_ice",
        "category_label": "Snow or ice",
        "description": "Snowbank over the pad",
        "status": "open",
        "status_label": "Open",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "resolved_at": None,
    }
    history = conn.execute("SELECT * FROM report_status_history WHERE report_id = ?",
                           (report["id"],)).fetchall()
    assert len(history) == 1
    assert history[0]["old_status"] is None
    assert history[0]["new_status"] == "open"
    assert history[0]["changed_by"] == user["id"]
    assert history[0]["changed_at"] == NOW.isoformat()


def test_fourth_report_at_one_stop_within_an_hour_is_rate_limited(client, clock):
    login(client)
    for minute in (0, 10, 20):
        clock.now = NOW + timedelta(minutes=minute)
        assert submit(client).status_code == 201
    clock.now = NOW + timedelta(minutes=30)
    res = submit(client)
    assert res.status_code == 429
    body = res.get_json()
    # The first report (at minute 0) ages out at minute 60, 30 minutes from now.
    assert body["retry_after_minutes"] == 30
    assert "error" in body

    # Another stop is still fine.
    assert submit(client, stop="FAIRWAY").status_code == 201

    clock.now = NOW + timedelta(minutes=60)
    assert submit(client).status_code == 201


def test_eleventh_report_in_a_day_is_rate_limited(client, clock):
    login(client)
    for i, stop in enumerate(OTHER_STOPS):
        clock.now = NOW + timedelta(minutes=5 * i)
        assert submit(client, stop=stop).status_code == 201
    clock.now = NOW + timedelta(hours=2)
    res = submit(client)
    assert res.status_code == 429
    # The first report ages out 24 h after NOW, which is 22 h from now.
    assert res.get_json()["retry_after_minutes"] == 22 * 60

    clock.now = NOW + timedelta(hours=24)
    assert submit(client).status_code == 201


def test_rate_limit_is_per_user(client, clock):
    login(client)
    for _ in range(3):
        assert submit(client).status_code == 201
    assert submit(client).status_code == 429
    login(client, "sam", "password123")
    assert submit(client).status_code == 201


def test_rate_limit_wait_helper(conn):
    user = auth.create_user(conn, "helper", "password123")
    assert barriers.rate_limit_wait(conn, user["id"], STOP, NOW) == 0
    for minute in (0, 1, 2):
        barriers.create_report(conn, STOP, user["id"], "other", "x", NOW + timedelta(minutes=minute))
    assert barriers.rate_limit_wait(conn, user["id"], STOP, NOW + timedelta(minutes=2)) == 58
    assert barriers.rate_limit_wait(conn, user["id"], STOP, NOW + timedelta(minutes=59, seconds=30)) == 1
    assert barriers.rate_limit_wait(conn, user["id"], STOP, NOW + timedelta(minutes=60)) == 0
    assert barriers.rate_limit_wait(conn, user["id"], "FAIRWAY", NOW + timedelta(minutes=2)) == 0


def _insert(conn, user_id, status, created, resolved=None, stop=STOP, category="ramp"):
    cur = conn.execute(
        """INSERT INTO barrier_reports (stop_id, user_id, category, description, status,
                                        created_at, updated_at, resolved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (stop, user_id, category, f"{status} report", status, created.isoformat(),
         (resolved or created).isoformat(), resolved.isoformat() if resolved else None))
    conn.commit()
    return cur.lastrowid


def test_stop_reports_hide_resolved_by_default_and_never_show_usernames(client, conn):
    sam = conn.execute("SELECT id FROM users WHERE username = 'sam'").fetchone()["id"]
    older = _insert(conn, sam, "open", NOW - timedelta(days=2))
    newer = _insert(conn, sam, "under_review", NOW - timedelta(days=1))
    recent_fix = _insert(conn, sam, "resolved", NOW - timedelta(days=5), NOW - timedelta(days=3))
    _insert(conn, sam, "resolved", NOW - timedelta(days=50), NOW - timedelta(days=40))  # too old
    _insert(conn, sam, "open", NOW, stop="FAIRWAY")  # other stop

    data = client.get(f"/api/stops/{STOP}/reports").get_json()
    assert data["stop_id"] == STOP
    assert [r["id"] for r in data["reports"]] == [newer, older]

    data = client.get(f"/api/stops/{STOP}/reports?include_resolved=1").get_json()
    assert [r["id"] for r in data["reports"]] == [newer, older, recent_fix]
    assert data["reports"][2]["status_label"] == "Resolved"

    text = client.get(f"/api/stops/{STOP}/reports?include_resolved=1").get_data(as_text=True)
    assert "sam" not in text
    for report in data["reports"]:
        assert "username" not in report and "user_id" not in report and "reported_by" not in report


def test_list_is_public(client):
    login(client)
    submit(client)
    client.post("/api/auth/logout")
    res = client.get(f"/api/stops/{STOP}/reports")
    assert res.status_code == 200
    assert len(res.get_json()["reports"]) == 1
