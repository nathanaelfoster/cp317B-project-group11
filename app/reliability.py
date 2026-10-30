"""UI-1: Historical Delay Display.

Average delay and on-time percentage for a stop or route, filtered by day of
week and time of day, built from recorded arrivals in trip_updates.
"""
from . import delays

MIN_TRIPS_FOR_CONFIDENCE = 10


def _filters(day, time_of_day):
    """SQL conditions and parameters for the day-of-week and time-of-day filters.

    TODO(UI-1): return (clauses, params) where clauses is a list of SQL
    strings that get ANDed into the query in _report() below, and params are
    their ? values in order.

      day          "all", or a key from delays.DAY_OF_WEEK ("weekday", "saturday", "sunday").
                   Filter on tu.service_dow (0 = Monday ... 6 = Sunday).
      time_of_day  "all", or a key from delays.TIME_OF_DAY ("early", "am_peak", ...).
                   Filter on tu.scheduled_secs (seconds after midnight) using the
                   start hour (inclusive) and end hour (exclusive).

    "all" (or None) means no condition. Raise ValueError for an unknown key;
    the API turns that into a 400 error.

    Example: _filters("weekday", "am_peak") could return
      (["tu.service_dow IN (?,?,?,?,?)", "tu.scheduled_secs >= ? AND tu.scheduled_secs < ?"],
       [0, 1, 2, 3, 4, 25200, 36000])
    """
    raise NotImplementedError("UI-1: _filters")


def _report(conn, where, params, day, time_of_day):
    clauses, filter_params = _filters(day, time_of_day)
    sql = f"""SELECT tu.route_id, r.short_name, r.long_name, tu.delay_seconds, tu.cancelled
              FROM trip_updates tu JOIN routes r ON r.route_id = tu.route_id
              WHERE {' AND '.join([where] + clauses)}"""
    by_route, all_delays, cancelled = {}, [], 0
    for row in conn.execute(sql, [*params, *filter_params]):
        entry = by_route.setdefault(row["route_id"], {
            "route_id": row["route_id"], "short_name": row["short_name"],
            "long_name": row["long_name"], "delays": [], "cancelled": 0})
        if row["cancelled"]:
            entry["cancelled"] += 1
            cancelled += 1
        elif row["delay_seconds"] is not None:
            entry["delays"].append(row["delay_seconds"])
            all_delays.append(row["delay_seconds"])

    routes = []
    for entry in sorted(by_route.values(), key=lambda e: e["short_name"] or ""):
        summary = delays.summarize(entry.pop("delays"))
        routes.append({**entry, **summary,
                       "limited_data": summary["trips"] < MIN_TRIPS_FOR_CONFIDENCE})
    overall = delays.summarize(all_delays)
    return {
        "filters": {"day": day or "all", "time": time_of_day or "all"},
        "overall": {**overall, "cancelled": cancelled,
                    "limited_data": overall["trips"] < MIN_TRIPS_FOR_CONFIDENCE},
        "routes": routes,
    }


def stop_reliability(conn, stop_id, day="all", time_of_day="all"):
    return _report(conn, "tu.stop_id = ?", [stop_id], day, time_of_day)


def route_reliability(conn, route_id, day="all", time_of_day="all"):
    return _report(conn, "tu.route_id = ?", [route_id], day, time_of_day)
