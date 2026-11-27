"""UI-6a Part 2: admin report list, status changes and the open_reports badge."""
from datetime import timedelta

import pytest

from app import auth, barriers
from app.api import create_app

from .conftest import NOW
from .test_barriers import Clock, login, submit

STOP = "UNIV_KING"


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def client(conn, db_path, clock):
    auth.seed_demo_users(conn)
    return create_app(db_path=db_path, now_fn=clock).test_client()


@pytest.fixture
def report_id(client):
    login(client, "rider_demo")
    rid = submit(client).get_json()["id"]
    client.post("/api/auth/logout")
    return rid


def patch(client, rid, status):
    return client.patch(f"/api/reports/{rid}", json={"status": status})


def test_admin_moves_open_to_under_review_to_resolved(client, conn, clock, report_id):
    admin = login(client, "admin_demo")

    clock.now = NOW + timedelta(hours=2)
    res = patch(client, report_id, "under_review")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "under_review" and body["status_label"] == "Under review"
    assert body["updated_at"] == clock.now.isoformat()
    assert body["resolved_at"] is None

    clock.now = NOW + timedelta(hours=30)
    res = patch(client, report_id, "resolved")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] == clock.now.isoformat()
    assert body["created_at"] == NOW.isoformat()

    history = conn.execute(
        "SELECT old_status, new_status, changed_by FROM report_status_history WHERE report_id = ? ORDER BY id",
        (report_id,)).fetchall()
    assert [(h["old_status"], h["new_status"]) for h in history] == [
        (None, "open"), ("open", "under_review"), ("under_review", "resolved")]
    assert history[1]["changed_by"] == history[2]["changed_by"] == admin["id"]


def test_send_back_to_open_clears_resolved_at(client, report_id):
    login(client, "admin_demo")
    assert patch(client, report_id, "under_review").status_code == 200
    res = patch(client, report_id, "open")
    assert res.status_code == 200
    assert res.get_json()["status"] == "open"
    assert res.get_json()["resolved_at"] is None


def test_open_to_resolved_returns_409_with_allowed(client, report_id):
    login(client, "admin_demo")
    res = patch(client, report_id, "resolved")
    assert res.status_code == 409
    assert res.get_json() == {"error": "Can't move a report from open to resolved", "allowed": ["under_review"]}


def test_nothing_moves_out_of_resolved(client, report_id):
    login(client, "admin_demo")
    patch(client, report_id, "under_review")
    patch(client, report_id, "resolved")
    for status in ("open", "under_review", "resolved"):
        res = patch(client, report_id, status)
        assert res.status_code == 409
        assert res.get_json()["allowed"] == []


def test_patch_bad_status_and_unknown_report(client, report_id):
    login(client, "admin_demo")
    assert patch(client, report_id, "fixed").status_code == 400
    assert client.patch(f"/api/reports/{report_id}", json={}).status_code == 400
    assert patch(client, 99999, "under_review").status_code == 404


@pytest.mark.parametrize("username", ["rider_demo", "analyst_demo"])
def test_rider_and_analyst_get_403_on_patch(client, conn, report_id, username):
    login(client, username)
    assert patch(client, report_id, "under_review").status_code == 403
    assert client.get("/api/reports").status_code == 403
    status = conn.execute("SELECT status FROM barrier_reports WHERE id = ?", (report_id,)).fetchone()[0]
    assert status == "open"


def test_logged_out_admin_endpoints_return_401(client, report_id):
    assert patch(client, report_id, "under_review").status_code == 401
    assert client.get("/api/reports").status_code == 401


def test_admin_list_includes_reported_by_and_filters_by_status(client, clock, report_id):
    login(client, "admin_demo")
    clock.now = NOW + timedelta(minutes=5)
    second = submit(client, stop="FAIRWAY", category="elevator", description="Lift is down").get_json()["id"]
    patch(client, second, "under_review")

    reports = client.get("/api/reports").get_json()["reports"]
    assert [r["id"] for r in reports] == [second, report_id]
    assert {r["reported_by"] for r in reports} == {"admin_demo", "rider_demo"}

    open_only = client.get("/api/reports?status=open").get_json()["reports"]
    assert [r["id"] for r in open_only] == [report_id]
    assert open_only[0]["reported_by"] == "rider_demo"
    assert client.get("/api/reports?status=nope").status_code == 400


def test_stop_detail_includes_open_reports(client, report_id):
    assert client.get(f"/api/stops/{STOP}").get_json()["open_reports"] == 1
    assert client.get("/api/stops/FAIRWAY").get_json()["open_reports"] == 0

    login(client, "admin_demo")
    patch(client, report_id, "under_review")
    assert client.get(f"/api/stops/{STOP}").get_json()["open_reports"] == 1  # under review still counts
    patch(client, report_id, "resolved")
    assert client.get(f"/api/stops/{STOP}").get_json()["open_reports"] == 0


def test_resolved_report_shows_with_include_resolved(client, report_id):
    login(client, "admin_demo")
    patch(client, report_id, "under_review")
    patch(client, report_id, "resolved")
    assert client.get(f"/api/stops/{STOP}/reports").get_json()["reports"] == []
    shown = client.get(f"/api/stops/{STOP}/reports?include_resolved=1").get_json()["reports"]
    assert [r["id"] for r in shown] == [report_id]
    assert "reported_by" not in shown[0]


def test_change_status_helper_errors(conn):
    with pytest.raises(LookupError):
        barriers.change_status(conn, 1, "under_review", None, NOW)
