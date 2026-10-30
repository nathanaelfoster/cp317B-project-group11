"""UI-1 Historical Delay Display acceptance tests."""
from datetime import date

import pytest

from app import reliability, timeutil


def add(conn, trip_id, service_date, secs, delay, stop_id="UNIV_KING", route_id="7", cancelled=False):
    sched = timeutil.scheduled_datetime(service_date, secs)
    conn.execute(
        """INSERT INTO trip_updates (trip_id, stop_id, route_id, service_date, service_dow,
               scheduled_secs, scheduled_arrival, predicted_arrival, delay_seconds, cancelled, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (trip_id, stop_id, route_id, service_date.isoformat(), service_date.weekday(), secs,
         sched.isoformat(), None, None if cancelled else delay, int(cancelled), sched.isoformat()))


WED = date(2026, 10, 28)
SAT = date(2026, 10, 31)


@pytest.fixture
def history(conn):
    trips = [r["trip_id"] for r in conn.execute(
        "SELECT trip_id FROM trips WHERE route_id = '7' LIMIT 6")]
    add(conn, trips[0], WED, 8 * 3600, 60)        # weekday AM peak, on time
    add(conn, trips[1], WED, 8 * 3600 + 600, 600)  # weekday AM peak, late
    add(conn, trips[2], WED, 16 * 3600, 420)       # weekday PM peak, late
    add(conn, trips[3], SAT, 16 * 3600, 0)         # Saturday PM peak, on time
    add(conn, trips[4], WED, 17 * 3600, None, cancelled=True)
    add(conn, trips[5], WED, 12 * 3600, 30, stop_id="PUBLIC_SQUARE")  # different stop
    conn.commit()
    return conn


def test_all_history_for_a_stop(history):
    report = reliability.stop_reliability(history, "UNIV_KING")
    overall = report["overall"]
    assert overall["trips"] == 4
    assert overall["on_time"] == 2
    assert overall["on_time_pct"] == 50
    assert overall["cancelled"] == 1
    assert [r["short_name"] for r in report["routes"]] == ["7"]


def test_filter_by_day_of_week(history):
    weekday = reliability.stop_reliability(history, "UNIV_KING", day="weekday")
    saturday = reliability.stop_reliability(history, "UNIV_KING", day="saturday")
    assert weekday["overall"]["trips"] == 3
    assert saturday["overall"]["trips"] == 1
    assert saturday["overall"]["on_time_pct"] == 100


def test_filter_by_time_of_day(history):
    am = reliability.stop_reliability(history, "UNIV_KING", time_of_day="am_peak")
    pm = reliability.stop_reliability(history, "UNIV_KING", time_of_day="pm_peak")
    assert am["overall"]["trips"] == 2
    assert am["overall"]["avg_delay_min"] == 5.5
    assert pm["overall"]["trips"] == 2


def test_filters_combine(history):
    report = reliability.stop_reliability(history, "UNIV_KING", day="weekday", time_of_day="pm_peak")
    assert report["overall"]["trips"] == 1
    assert report["overall"]["on_time"] == 0


def test_small_samples_are_flagged_as_limited(history):
    report = reliability.stop_reliability(history, "UNIV_KING")
    assert report["overall"]["limited_data"] is True


def test_route_reliability(history):
    report = reliability.route_reliability(history, "7")
    assert report["overall"]["trips"] == 5


def test_unknown_filter_is_rejected(history):
    with pytest.raises(ValueError):
        reliability.stop_reliability(history, "UNIV_KING", day="funday")
