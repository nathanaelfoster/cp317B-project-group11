"""UI-3: Live arrivals with service alerts.

Turns what the collector recorded (REP-3) into what a rider reads on the stop
screen: a status for every arrival, whether its route is on a detour, and a
plain label for each alert's effect.
"""
from . import delays

# GTFS-Realtime alert effects riders are most likely to see. Anything else
# (including UNKNOWN_EFFECT, which GRT often sends) reads as "Service change".
EFFECT_LABELS = {
    "DETOUR": "Detour",
    "REDUCED_SERVICE": "Reduced service",
    "NO_SERVICE": "No service",
    "SIGNIFICANT_DELAYS": "Significant delays",
    "STOP_MOVED": "Stop moved",
}
DEFAULT_EFFECT_LABEL = "Service change"


def arrival_status(delay_seconds, cancelled, has_prediction):
    """(status, status_label) for one arrival.

    status is the REP-1 word ("Early", "On time", "Late"), or "Cancelled", or
    "Scheduled" when there is no live prediction. status_label is what riders
    read, e.g. "Late 6 min". The on-time window comes from app/delays.py.
    """
    if cancelled:
        return "Cancelled", delays.status_label(delay_seconds, cancelled=True)
    # Without a live prediction the delay means nothing, so fall back to the timetable.
    if not has_prediction or delay_seconds is None:
        return "Scheduled", delays.status_label(None)
    return delays.classify(delay_seconds), delays.status_label(delay_seconds)


def effect_label(effect):
    """Rider label for a GTFS-Realtime effect name, e.g. "DETOUR" -> "Detour"."""
    return EFFECT_LABELS.get(effect, DEFAULT_EFFECT_LABEL)


def detoured_routes(conn, now, stop_id):
    """Route ids serving this stop that have an active DETOUR alert.

    An alert that names routes puts only those routes on detour, even when it
    also names the stop ("Route 7 on detour at King St." should not flag the
    201). An alert that names this stop but no routes puts every route here
    on detour.
    """
    t = now.isoformat()
    serving = {r["route_id"] for r in conn.execute(
        """SELECT DISTINCT t.route_id FROM stop_times st JOIN trips t ON t.trip_id = st.trip_id
           WHERE st.stop_id = ?""", (stop_id,))}
    entities = {}
    for row in conn.execute(
            """SELECT ae.alert_id, ae.route_id, ae.stop_id FROM alerts a
               JOIN alert_entities ae ON ae.alert_id = a.alert_id
               WHERE a.active = 1 AND a.effect = 'DETOUR'
                 AND (a.active_start IS NULL OR a.active_start <= ?)
                 AND (a.active_end IS NULL OR a.active_end >= ?)""", (t, t)):
        entities.setdefault(row["alert_id"], []).append(row)

    routes = set()
    for rows in entities.values():
        named = {r["route_id"] for r in rows if r["route_id"]}
        if named:
            routes |= named & serving
        elif any(r["stop_id"] == stop_id for r in rows):
            routes |= serving
    return routes
