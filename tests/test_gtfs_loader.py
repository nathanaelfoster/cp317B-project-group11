"""REP-2 Transit Data Storage tests."""
from datetime import date

import pytest

from app import timeutil
from app.gtfs_loader import load_gtfs


def test_sample_feed_loads(conn):
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["stops", "routes", "trips", "stop_times"]}
    assert counts["stops"] == 11
    assert counts["routes"] == 4
    assert counts["trips"] > 0 and counts["stop_times"] > counts["trips"]


def test_wheelchair_accessibility_is_stored(conn):
    row = conn.execute("SELECT wheelchair_boarding FROM stops WHERE stop_id = 'ALBERT_SEAGRAM'").fetchone()
    assert row["wheelchair_boarding"] == 2
    row = conn.execute("SELECT wheelchair_boarding FROM stops WHERE stop_id = 'UNIV_KING'").fetchone()
    assert row["wheelchair_boarding"] == 1


def test_reloading_replaces_rather_than_duplicates(conn):
    from app import config
    load_gtfs(conn, config.SAMPLE_GTFS_DIR)
    assert conn.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 11


def test_service_calendar(conn):
    assert timeutil.active_service_ids(conn, date(2026, 10, 28)) == {"WKDY"}
    assert timeutil.active_service_ids(conn, date(2026, 10, 31)) == {"WKND"}


def test_gtfs_times_past_midnight():
    assert timeutil.parse_gtfs_time("25:10:00") == 25 * 3600 + 600


def test_missing_files_are_reported(conn, tmp_path):
    with pytest.raises(ValueError, match="stops.txt"):
        load_gtfs(conn, tmp_path)
