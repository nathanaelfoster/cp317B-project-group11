"""REP-3 Automated Data Collection tests."""
from datetime import timedelta

from google.transit import gtfs_realtime_pb2

from app import collector, timeutil
from app.collector import SampleFeedSource, collect_once

from .conftest import NOW, empty_feed


def test_collection_stores_trip_updates_and_alerts(conn):
    assert collect_once(conn, SampleFeedSource(), NOW) is True
    assert conn.execute("SELECT COUNT(*) FROM trip_updates").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE active = 1").fetchone()[0] == 1
    log = conn.execute("SELECT * FROM collection_log").fetchone()
    assert log["success"] == 1 and log["trip_updates"] > 0


def test_updates_are_linked_to_trip_and_stop_with_delay(conn):
    st = conn.execute(
        """SELECT st.trip_id, st.stop_sequence, st.arrival_secs FROM stop_times st
           JOIN trips t ON t.trip_id = st.trip_id
           WHERE st.stop_id = 'UNIV_KING' AND t.route_id = '7' AND t.service_id = 'WKDY'
             AND st.arrival_secs >= ? ORDER BY st.arrival_secs LIMIT 1""",
        (16 * 3600 + 30 * 60,)).fetchone()
    trip_id = st["trip_id"]
    feed = empty_feed()
    e = feed.entity.add(id="1")
    e.trip_update.trip.trip_id = trip_id
    e.trip_update.trip.start_date = "20261028"
    stu = e.trip_update.stop_time_update.add(stop_sequence=st["stop_sequence"], stop_id="UNIV_KING")
    scheduled = timeutil.scheduled_datetime(NOW.date(), st["arrival_secs"])
    stu.arrival.time = int((scheduled + timedelta(minutes=4)).timestamp())

    assert collector.store_trip_updates(conn, feed, NOW) == 1
    row = conn.execute("SELECT * FROM trip_updates").fetchone()
    assert (row["trip_id"], row["stop_id"], row["route_id"]) == (trip_id, "UNIV_KING", "7")
    assert row["service_date"] == "2026-10-28"
    assert row["delay_seconds"] == 240
    assert row["recorded_at"] == NOW.isoformat()


def test_newer_prediction_overwrites_older_one(conn):
    collect_once(conn, SampleFeedSource(), NOW)
    first = conn.execute("SELECT COUNT(*) FROM trip_updates").fetchone()[0]
    collect_once(conn, SampleFeedSource(), NOW + timedelta(seconds=30))
    assert conn.execute("SELECT COUNT(*) FROM trip_updates").fetchone()[0] >= first
    dupes = conn.execute("""SELECT COUNT(*) FROM (SELECT 1 FROM trip_updates
                            GROUP BY trip_id, stop_id, service_date HAVING COUNT(*) > 1)""").fetchone()[0]
    assert dupes == 0


def test_cancelled_trip_is_recorded(conn):
    trip_id = conn.execute("SELECT trip_id FROM trips WHERE route_id = '9' LIMIT 1").fetchone()["trip_id"]
    feed = empty_feed()
    e = feed.entity.add(id="1")
    e.trip_update.trip.trip_id = trip_id
    e.trip_update.trip.start_date = "20261028"
    e.trip_update.trip.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.CANCELED
    stored = collector.store_trip_updates(conn, feed, NOW)
    assert stored == 3  # route 9 has three stops
    assert conn.execute("SELECT COUNT(*) FROM trip_updates WHERE cancelled = 1").fetchone()[0] == 3


def test_unknown_trips_are_ignored(conn):
    feed = empty_feed()
    e = feed.entity.add(id="1")
    e.trip_update.trip.trip_id = "not-a-real-trip"
    e.trip_update.stop_time_update.add(stop_sequence=1).arrival.delay = 60
    assert collector.store_trip_updates(conn, feed, NOW) == 0


class BrokenSource:
    def trip_updates(self, conn, now):
        raise ConnectionError("GRT feed unreachable")

    def alerts(self, conn, now):
        raise AssertionError("not reached")


def test_failed_attempts_are_logged_not_raised(conn):
    assert collect_once(conn, BrokenSource(), NOW) is False
    log = conn.execute("SELECT * FROM collection_log").fetchone()
    assert log["success"] == 0
    assert "GRT feed unreachable" in log["message"]


def test_alerts_missing_from_feed_become_inactive(conn):
    collect_once(conn, SampleFeedSource(), NOW)
    collector.store_alerts(conn, empty_feed(), NOW)
    assert conn.execute("SELECT COUNT(*) FROM alerts WHERE active = 1").fetchone()[0] == 0
