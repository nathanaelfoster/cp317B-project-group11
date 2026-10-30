"""Sample-mode data: a simulated GTFS-Realtime feed and seeded arrival history.

Lets the whole pipeline (collector -> database -> API -> UI) run offline. All
delays here are generated, not recorded from GRT.
"""
import random
from datetime import timedelta

from google.transit import gtfs_realtime_pb2

from . import timeutil

# Mean and spread of delay in seconds for each sample route.
ROUTE_PROFILES = {"7": (150, 200), "201": (45, 90), "301": (15, 60), "9": (110, 240)}
PEAK_EXTRA = {"am_peak": 60, "pm_peak": 150}
CANCEL_RATE = 0.02


def _peak(secs):
    hour = secs // 3600
    if 7 <= hour < 10:
        return "am_peak"
    if 15 <= hour < 19:
        return "pm_peak"
    return None


def trip_delay(route_id, trip_id, service_date, start_secs):
    """Deterministic (delay at first stop, extra delay per stop, cancelled) for a trip."""
    rnd = random.Random(f"{trip_id}|{service_date.isoformat()}")
    mean, spread = ROUTE_PROFILES.get(route_id, (60, 120))
    base = rnd.gauss(mean + PEAK_EXTRA.get(_peak(start_secs), 0), spread)
    drift = rnd.gauss(10, 15)
    cancelled = rnd.random() < CANCEL_RATE
    return max(-150, int(base)), int(drift), cancelled


def _trip_stop_times(conn, service_ids, lo_secs, hi_secs):
    """Stop times for trips that are running at some point in [lo_secs, hi_secs]."""
    if not service_ids:
        return {}
    marks = ",".join("?" * len(service_ids))
    rows = conn.execute(
        f"""SELECT st.trip_id, st.stop_id, st.stop_sequence, st.arrival_secs, t.route_id
            FROM stop_times st JOIN trips t ON t.trip_id = st.trip_id
            WHERE t.service_id IN ({marks}) AND st.trip_id IN (
                SELECT trip_id FROM stop_times GROUP BY trip_id
                HAVING MAX(arrival_secs) >= ? AND MIN(arrival_secs) <= ?)
            ORDER BY st.trip_id, st.stop_sequence""",
        (*service_ids, lo_secs, hi_secs),
    )
    trips = {}
    for row in rows:
        trips.setdefault(row["trip_id"], []).append(row)
    return trips


def build_trip_updates_feed(conn, now):
    """A GTFS-Realtime TripUpdates message for trips running in the next hour."""
    service_date = now.date()
    now_secs = timeutil.secs_since_midnight(now, service_date)
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(now.timestamp())

    service_ids = timeutil.active_service_ids(conn, service_date)
    for trip_id, stops in _trip_stop_times(conn, service_ids, now_secs - 1800, now_secs + 3600).items():
        base, drift, cancelled = trip_delay(stops[0]["route_id"], trip_id, service_date,
                                            stops[0]["arrival_secs"])
        entity = feed.entity.add()
        entity.id = trip_id
        tu = entity.trip_update
        tu.trip.trip_id = trip_id
        tu.trip.start_date = service_date.strftime("%Y%m%d")
        if cancelled:
            tu.trip.schedule_relationship = gtfs_realtime_pb2.TripDescriptor.CANCELED
            continue
        for i, st in enumerate(stops):
            delay = base + i * drift
            predicted = timeutil.scheduled_datetime(service_date, st["arrival_secs"]) + timedelta(seconds=delay)
            if predicted < now - timedelta(minutes=2):
                continue  # real feeds drop stops the vehicle has already passed
            stu = tu.stop_time_update.add()
            stu.stop_sequence = st["stop_sequence"]
            stu.stop_id = st["stop_id"]
            stu.arrival.time = int(predicted.timestamp())
            stu.arrival.delay = delay
        if not tu.stop_time_update:
            del feed.entity[-1]
    return feed


def build_alerts_feed(now):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(now.timestamp())
    entity = feed.entity.add()
    entity.id = "sample-detour-7"
    alert = entity.alert
    alert.effect = gtfs_realtime_pb2.Alert.DETOUR
    alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
    alert.header_text.translation.add(text="Route 7 on detour at King St. Expect delays.", language="en")
    alert.description_text.translation.add(
        text="Sample alert: construction near University Ave. Buses may arrive up to 10 minutes late.",
        language="en")
    period = alert.active_period.add()
    period.start = int((now - timedelta(hours=2)).timestamp())
    period.end = int((now + timedelta(hours=6)).timestamp())
    alert.informed_entity.add(route_id="7")
    alert.informed_entity.add(stop_id="UNIV_KING")
    return feed


def seed_history(conn, days=28, today=None):
    """Fill trip_updates with `days` days of simulated recorded arrivals."""
    today = today or timeutil.now_local().date()
    recorded = 0
    for back in range(days, 0, -1):
        service_date = today - timedelta(days=back)
        service_ids = timeutil.active_service_ids(conn, service_date)
        rows = []
        for trip_id, stops in _trip_stop_times(conn, service_ids, 0, 48 * 3600).items():
            route_id = stops[0]["route_id"]
            base, drift, cancelled = trip_delay(route_id, trip_id, service_date, stops[0]["arrival_secs"])
            for i, st in enumerate(stops):
                scheduled = timeutil.scheduled_datetime(service_date, st["arrival_secs"])
                delay = None if cancelled else base + i * drift
                predicted = None if cancelled else scheduled + timedelta(seconds=delay)
                rows.append((
                    trip_id, st["stop_id"], route_id, service_date.isoformat(), service_date.weekday(),
                    st["arrival_secs"], scheduled.isoformat(),
                    predicted.isoformat() if predicted else None, delay, int(cancelled),
                    (predicted or scheduled).isoformat(),
                ))
        with conn:
            conn.executemany(
                """INSERT OR REPLACE INTO trip_updates
                   (trip_id, stop_id, route_id, service_date, service_dow, scheduled_secs,
                    scheduled_arrival, predicted_arrival, delay_seconds, cancelled, recorded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        recorded += len(rows)
    return recorded
