"""UI-6a: demo barrier reports for the class demo and REP-4a."""
from collections import Counter
from datetime import datetime, timedelta

import pytest

from app import auth, barriers

from .conftest import NOW


@pytest.fixture
def seeded(conn):
    auth.seed_demo_users(conn)
    assert barriers.seed_demo_reports(conn, NOW) == 25
    return conn


def test_about_25_reports_over_60_days_at_6_to_8_stops(seeded):
    rows = seeded.execute("SELECT * FROM barrier_reports").fetchall()
    assert len(rows) == 25
    assert 6 <= len({r["stop_id"] for r in rows}) <= 8
    for r in rows:
        created = datetime.fromisoformat(r["created_at"])
        assert NOW - timedelta(days=61) <= created < NOW


def test_mix_of_statuses_and_categories(seeded):
    statuses = Counter(r[0] for r in seeded.execute("SELECT status FROM barrier_reports"))
    assert statuses == {"resolved": 16, "under_review": 4, "open": 5}
    categories = {r[0] for r in seeded.execute("SELECT category FROM barrier_reports")}
    assert categories == set(barriers.CATEGORIES)


def test_resolution_times_are_hours_to_days_and_in_the_past(seeded):
    for r in seeded.execute("SELECT * FROM barrier_reports"):
        created, updated = datetime.fromisoformat(r["created_at"]), datetime.fromisoformat(r["updated_at"])
        assert created <= updated <= NOW
        if r["status"] == "resolved":
            hours = (datetime.fromisoformat(r["resolved_at"]) - created).total_seconds() / 3600
            assert 3 <= hours <= 5 * 24
            assert r["resolved_at"] == r["updated_at"]
        else:
            assert r["resolved_at"] is None


def test_history_matches_each_report(seeded):
    for r in seeded.execute("SELECT * FROM barrier_reports"):
        steps = seeded.execute(
            "SELECT old_status, new_status, changed_at FROM report_status_history WHERE report_id = ? ORDER BY id",
            (r["id"],)).fetchall()
        assert steps[0]["old_status"] is None and steps[0]["new_status"] == "open"
        assert steps[0]["changed_at"] == r["created_at"]
        assert steps[-1]["new_status"] == r["status"]
        expected = {"open": 1, "under_review": 2, "resolved": 3}[r["status"]]
        assert len(steps) == expected


def test_university_king_is_the_hotspot(seeded):
    top = seeded.execute(
        "SELECT stop_id, COUNT(*) AS n FROM barrier_reports GROUP BY stop_id ORDER BY n DESC LIMIT 1").fetchone()
    assert (top["stop_id"], top["n"]) == ("UNIV_KING", 6)


def test_seed_is_idempotent(seeded):
    assert barriers.seed_demo_reports(seeded, NOW) == 0
    assert seeded.execute("SELECT COUNT(*) FROM barrier_reports").fetchone()[0] == 25


def test_seed_needs_demo_users(conn):
    with pytest.raises(LookupError):
        barriers.seed_demo_reports(conn, NOW)


def test_seeded_reports_show_through_the_api(seeded, db_path):
    from app.api import create_app
    client = create_app(db_path=db_path, now_fn=lambda: NOW).test_client()
    assert client.get("/api/stops/UNIV_KING").get_json()["open_reports"] == 2
    reports = client.get("/api/stops/UNIV_KING/reports").get_json()["reports"]
    assert [r["status"] for r in reports] == ["open", "under_review"]


def test_run_reset_seeds_users_and_reports(tmp_path, monkeypatch):
    import sqlite3

    import run
    from app import config
    db_file = tmp_path / "demo.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", db_file)
    run.setup(reset=True)
    c = sqlite3.connect(db_file)
    assert c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 3
    assert c.execute("SELECT COUNT(*) FROM barrier_reports").fetchone()[0] == 25
    c.close()
