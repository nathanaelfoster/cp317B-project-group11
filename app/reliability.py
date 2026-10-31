"""UI-1: Historical Delay Display.

Average delay and on-time percentage for a stop or route, filtered by day of
week and time of day, built from recorded arrivals in trip_updates.
"""
from . import delays

MIN_TRIPS_FOR_CONFIDENCE = 10


def _filters(day, time_of_day):
    
    clauses = []
    params = []

    # Filter by day of week
    if day not in (None, "all"):
        day_groups = {
            key: weekdays
            for key, _, weekdays in delays.DAY_OF_WEEK
        }

        if day not in day_groups:
            raise ValueError(f"Unknown day filter: {day}")

        weekdays = day_groups[day]
        placeholders = ", ".join("?" for _ in weekdays)

        clauses.append(f"tu.service_dow IN ({placeholders})")
        params.extend(weekdays)

    # Filter by time of day
    if time_of_day not in (None, "all"):
        periods = {
            key: (start, end)
            for key, _, start, end in delays.TIME_OF_DAY
        }

        if time_of_day not in periods:
            raise ValueError(f"Unknown time-of-day filter: {time_of_day}")

        start_hour, end_hour = periods[time_of_day]

        clauses.append(
            "tu.scheduled_secs >= ? AND tu.scheduled_secs < ?"
        )
        params.extend((start_hour * 3600, end_hour * 3600))

    return clauses, params



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
