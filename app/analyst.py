"""REP-4: Analyst reports.

Three read-only reports for transit analysts and admins:
  - the least reliable accessible routes (from REP-3 recorded arrivals, REP-1
    on-time rule, UI-5 accessible filter and UI-1 day/time filters)
  - the stops with the most barrier reports (UI-6)
  - how long barrier reports take to resolve (UI-6)
"""
from datetime import datetime, timedelta
from statistics import mean, median

from . import accessibility, barriers, delays
from .reliability import _filters


def least_reliable_accessible_routes(conn, now, days=30, dow=None, time=None, limit=10, min_trips=20):
    """Routes whose accessible trips run on time least often, worst first.

    Only trips marked wheelchair accessible count. Cancelled trips are left out
    of the on-time % but counted in `cancelled`. Routes with fewer than
    `min_trips` measured trips are dropped, so a handful of trips can't put a
    route at the top. dow / time use the same keys as the reliability screen.
    """
    clauses, params = _filters(dow, time)
    since = (now.date() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        f"""SELECT tu.route_id, r.short_name, r.long_name, tu.delay_seconds, tu.cancelled
            FROM trip_updates tu
            JOIN trips t ON t.trip_id = tu.trip_id
            JOIN routes r ON r.route_id = tu.route_id
            WHERE {' AND '.join([accessibility.trip_sql("t"), "tu.service_date >= ?",
                                 "tu.service_date <= ?"] + clauses)}""",
        [since, now.date().isoformat(), *params])

    by_route = {}
    for row in rows:
        entry = by_route.setdefault(row["route_id"], {
            "route_id": row["route_id"], "route": row["short_name"], "long_name": row["long_name"],
            "delays": [], "cancelled": 0})
        if row["cancelled"]:
            entry["cancelled"] += 1
        elif row["delay_seconds"] is not None:
            entry["delays"].append(row["delay_seconds"])

    routes = []
    for entry in by_route.values():
        # REP-1 summarize: trips, on_time, on_time_pct and avg_delay_min with the one on-time rule.
        summary = delays.summarize(entry.pop("delays"))
        if summary["trips"] >= min_trips:
            routes.append({**entry, **summary})
    routes.sort(key=lambda r: (r["on_time_pct"], -r["trips"], r["route"] or ""))
    return {
        "filters": {"days": days, "day": dow or "all", "time": time or "all", "min_trips": min_trips},
        "routes": routes[:limit],
    }


def _reports_since(conn, now, days):
    """Barrier reports created in the last `days` days, with their stop name."""
    since = now - timedelta(days=days)
    rows = conn.execute(
        """SELECT br.id, br.stop_id, s.stop_name, br.category, br.status, br.created_at, br.resolved_at
           FROM barrier_reports br JOIN stops s ON s.stop_id = br.stop_id""").fetchall()
    # Compare as datetimes: stored times carry their own UTC offset, which changes with DST.
    return [r for r in rows if datetime.fromisoformat(r["created_at"]) >= since]


def report_hotspots(conn, now, days=90, limit=10):
    """Stops with the most barrier reports in the last `days` days, most first.

    For each stop: total, how many are open / under review / resolved, and the
    most common category (ties go to the category listed first in barriers.CATEGORIES).
    """
    by_stop = {}
    for r in _reports_since(conn, now, days):
        entry = by_stop.setdefault(r["stop_id"], {
            "stop_id": r["stop_id"], "stop_name": r["stop_name"], "total": 0,
            **{status: 0 for status in barriers.STATUSES}, "_categories": {}})
        entry["total"] += 1
        entry[r["status"]] += 1
        entry["_categories"][r["category"]] = entry["_categories"].get(r["category"], 0) + 1

    order = list(barriers.CATEGORIES)
    stops = []
    for entry in by_stop.values():
        counts = entry.pop("_categories")
        top = min(counts, key=lambda c: (-counts[c], order.index(c)))
        stops.append({**entry, "top_category": top, "top_category_label": barriers.CATEGORIES[top],
                      "top_category_count": counts[top]})
    # Most reports first; among equals, the stop with more still waiting on a fix.
    stops.sort(key=lambda s: (-s["total"], -(s["open"] + s["under_review"]), s["stop_name"]))
    return {"days": days, "stops": stops[:limit]}


def _time_summary(hours):
    if not hours:
        return {"resolved": 0, "avg_hours": None, "median_hours": None}
    return {"resolved": len(hours), "avg_hours": round(mean(hours), 1),
            "median_hours": round(median(hours), 1)}


def resolution_time(conn, now, days=90):
    """How long barrier reports take from submitted to resolved.

    Covers reports resolved in the last `days` days. Average and median hours
    overall and by category (median in Python, since SQLite has no MEDIAN),
    plus how many reports created in that window are still unresolved.
    """
    since = now - timedelta(days=days)
    rows = conn.execute(
        "SELECT category, status, created_at, resolved_at FROM barrier_reports").fetchall()

    overall, by_category, unresolved = [], {}, 0
    for r in rows:
        created = datetime.fromisoformat(r["created_at"])
        if r["status"] == "resolved" and r["resolved_at"]:
            resolved = datetime.fromisoformat(r["resolved_at"])
            if resolved >= since:
                hours = (resolved - created).total_seconds() / 3600
                overall.append(hours)
                by_category.setdefault(r["category"], []).append(hours)
        elif created >= since:
            unresolved += 1

    return {
        "days": days,
        **_time_summary(overall),
        "unresolved": unresolved,
        "by_category": [{"category": code, "label": label, **_time_summary(by_category[code])}
                        for code, label in barriers.CATEGORIES.items() if code in by_category],
    }
