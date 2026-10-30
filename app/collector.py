"""REP-3: Automated Data Collection.

Every 30 seconds, fetch GTFS-Realtime trip updates and service alerts, match
them to scheduled trips and stops, and store them. Every attempt is logged.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

import requests
from google.transit import gtfs_realtime_pb2

from . import config, db, delays, simulate, timeutil

log = logging.getLogger(__name__)

TripDescriptor = gtfs_realtime_pb2.TripDescriptor
StopTimeUpdate = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate


class HttpFeedSource:
    """Fetches GRT's live protobuf feeds."""

    def __init__(self, trip_updates_url=None, alerts_url=None, timeout=10):
        self.trip_updates_url = trip_updates_url or config.GRT_TRIP_UPDATES_URL
        self.alerts_url = alerts_url or config.GRT_ALERTS_URL
        self.timeout = timeout

    def _fetch(self, url):
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)
        return feed

    def trip_updates(self, conn, now):
        return self._fetch(self.trip_updates_url)

    def alerts(self, conn, now):
        return self._fetch(self.alerts_url)


class SampleFeedSource:
    """Simulated feeds built from the sample schedule, for offline demos."""

    def trip_updates(self, conn, now):
        return simulate.build_trip_updates_feed(conn, now)

    def alerts(self, conn, now):
        return simulate.build_alerts_feed(now)


def default_source():
    return SampleFeedSource() if config.MODE == "sample" else HttpFeedSource()


def _scheduled_stop(conn, trip_id, stu):
    if stu.HasField("stop_sequence"):
        row = conn.execute(
            "SELECT stop_id, arrival_secs FROM stop_times WHERE trip_id = ? AND stop_sequence = ?",
            (trip_id, stu.stop_sequence)).fetchone()
        if row:
            return row
    if stu.stop_id:
        return conn.execute(
            "SELECT stop_id, arrival_secs FROM stop_times WHERE trip_id = ? AND stop_id = ? "
            "ORDER BY stop_sequence LIMIT 1", (trip_id, stu.stop_id)).fetchone()
    return None


def _predicted(event, scheduled):
    if event.time:
        return datetime.fromtimestamp(event.time, tz=timeutil.TZ)
    if event.HasField("delay"):
        return scheduled + timedelta(seconds=event.delay)
    return None


UPSERT_SQL = """
INSERT INTO trip_updates
    (trip_id, stop_id, route_id, service_date, service_dow, scheduled_secs,
     scheduled_arrival, predicted_arrival, delay_seconds, cancelled, recorded_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (trip_id, stop_id, service_date) DO UPDATE SET
    predicted_arrival = excluded.predicted_arrival,
    delay_seconds = excluded.delay_seconds,
    cancelled = excluded.cancelled,
    recorded_at = excluded.recorded_at
"""


def store_trip_updates(conn, feed, now):
    """Match each stop time update to its scheduled trip and stop, then upsert it."""
    rows, unmatched = [], 0
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip = conn.execute("SELECT route_id FROM trips WHERE trip_id = ?",
                            (tu.trip.trip_id,)).fetchone()
        if trip is None:
            unmatched += 1
            continue
        service_date = (timeutil.parse_service_date(tu.trip.start_date)
                        if tu.trip.start_date else now.date())

        def row(stop_id, arrival_secs, predicted, cancelled):
            scheduled = timeutil.scheduled_datetime(service_date, arrival_secs)
            delay = None if predicted is None else delays.compute_delay_seconds(scheduled, predicted)
            return (tu.trip.trip_id, stop_id, trip["route_id"], service_date.isoformat(),
                    service_date.weekday(), arrival_secs, scheduled.isoformat(),
                    predicted.isoformat() if predicted else None, delay, int(cancelled),
                    now.isoformat())

        if tu.trip.schedule_relationship == TripDescriptor.CANCELED:
            for st in conn.execute("SELECT stop_id, arrival_secs FROM stop_times WHERE trip_id = ?",
                                   (tu.trip.trip_id,)):
                rows.append(row(st["stop_id"], st["arrival_secs"], None, True))
            continue

        for stu in tu.stop_time_update:
            st = _scheduled_stop(conn, tu.trip.trip_id, stu)
            if st is None:
                unmatched += 1
                continue
            if stu.schedule_relationship == StopTimeUpdate.SKIPPED:
                rows.append(row(st["stop_id"], st["arrival_secs"], None, True))
                continue
            scheduled = timeutil.scheduled_datetime(service_date, st["arrival_secs"])
            predicted = _predicted(stu.arrival, scheduled) or _predicted(stu.departure, scheduled)
            if predicted is not None:
                rows.append(row(st["stop_id"], st["arrival_secs"], predicted, False))

    with conn:
        conn.executemany(UPSERT_SQL, rows)
    if unmatched:
        log.debug("%d trip updates did not match the static schedule", unmatched)
    return len(rows)


def _text(translated):
    return translated.translation[0].text if translated.translation else ""


def store_alerts(conn, feed, now):
    """Record active alerts; alerts missing from the latest feed are marked inactive."""
    stamp = now.isoformat()
    with conn:
        conn.execute("UPDATE alerts SET active = 0")
        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue
            alert = entity.alert
            period = alert.active_period[0] if alert.active_period else None
            start = (datetime.fromtimestamp(period.start, tz=timeutil.TZ).isoformat()
                     if period and period.start else None)
            end = (datetime.fromtimestamp(period.end, tz=timeutil.TZ).isoformat()
                   if period and period.end else None)
            conn.execute(
                """INSERT INTO alerts (alert_id, header, description, effect, cause,
                       active_start, active_end, active, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT (alert_id) DO UPDATE SET
                       header = excluded.header, description = excluded.description,
                       effect = excluded.effect, cause = excluded.cause,
                       active_start = excluded.active_start, active_end = excluded.active_end,
                       active = 1, last_seen = excluded.last_seen""",
                (entity.id, _text(alert.header_text), _text(alert.description_text),
                 gtfs_realtime_pb2.Alert.Effect.Name(alert.effect),
                 gtfs_realtime_pb2.Alert.Cause.Name(alert.cause), start, end, stamp, stamp),
            )
            conn.execute("DELETE FROM alert_entities WHERE alert_id = ?", (entity.id,))
            conn.executemany(
                "INSERT INTO alert_entities (alert_id, route_id, stop_id) VALUES (?, ?, ?)",
                [(entity.id, ie.route_id or None, ie.stop_id or None) for ie in alert.informed_entity],
            )
    return sum(1 for e in feed.entity if e.HasField("alert"))


def collect_once(conn, source, now=None):
    """Run one collection cycle. Never raises: failures are logged to collection_log."""
    now = now or timeutil.now_local()
    started = time.monotonic()
    tu_count = alert_count = 0
    try:
        tu_count = store_trip_updates(conn, source.trip_updates(conn, now), now)
        alert_count = store_alerts(conn, source.alerts(conn, now), now)
        success, message = True, None
    except Exception as exc:  # network errors, bad protobufs, etc.
        log.warning("Collection failed: %s", exc)
        success, message = False, f"{type(exc).__name__}: {exc}"
    with conn:
        conn.execute(
            "INSERT INTO collection_log (attempted_at, success, trip_updates, alerts, duration_ms, message)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (now.isoformat(), int(success), tu_count, alert_count,
             int((time.monotonic() - started) * 1000), message),
        )
    return success


class Collector(threading.Thread):
    """Background thread that calls collect_once every POLL_SECONDS."""

    def __init__(self, db_path=None, source=None, interval=None):
        super().__init__(daemon=True, name="gtfs-rt-collector")
        self.db_path = db_path
        self.source = source or default_source()
        self.interval = interval or config.POLL_SECONDS
        self._stop = threading.Event()

    def run(self):
        conn = db.connect(self.db_path)
        log.info("Collector started (%s mode, every %ss)", config.MODE, self.interval)
        while not self._stop.is_set():
            started = time.monotonic()
            collect_once(conn, self.source)
            # Keep a steady 30 s cadence regardless of how long the cycle took.
            self._stop.wait(max(0, self.interval - (time.monotonic() - started)))
        conn.close()

    def stop(self):
        self._stop.set()
