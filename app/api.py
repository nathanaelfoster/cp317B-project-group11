"""Flask app: JSON API for the rider screens plus the static frontend."""
import math
from datetime import datetime, timedelta

from flask import Flask, abort, g, jsonify, request, send_from_directory

from . import accessibility, config, db, delays, reliability, timeutil, transfers

# Fixed "You are here" point so we never need to track the rider's location
# (Location Privacy). Roughly the University Ave. / King St. area.
DEFAULT_LOCATION = (43.4735, -80.5290)


def _distance_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def feed_status(conn, now):
    last_ok = conn.execute(
        "SELECT attempted_at FROM collection_log WHERE success = 1 ORDER BY id DESC LIMIT 1").fetchone()
    last_try = conn.execute(
        "SELECT attempted_at, success, message FROM collection_log ORDER BY id DESC LIMIT 1").fetchone()
    day_ago = (now - timedelta(days=1)).isoformat()
    stats = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(success), 0) AS ok FROM collection_log WHERE attempted_at >= ?",
        (day_ago,)).fetchone()
    last_ok_at = datetime.fromisoformat(last_ok["attempted_at"]) if last_ok else None
    live = bool(last_ok_at and (now - last_ok_at).total_seconds() <= config.STALE_AFTER_SECONDS)
    return {
        "mode": config.MODE,
        "live": live,
        "last_success": last_ok["attempted_at"] if last_ok else None,
        "last_attempt": last_try["attempted_at"] if last_try else None,
        "last_error": last_try["message"] if last_try and not last_try["success"] else None,
        "attempts_24h": stats["n"],
        "success_rate_24h": round(100 * stats["ok"] / stats["n"], 1) if stats["n"] else None,
    }


def stop_routes(conn, stop_id):
    return [dict(r) for r in conn.execute(
        """SELECT DISTINCT r.route_id, r.short_name, r.long_name FROM stop_times st
           JOIN trips t ON t.trip_id = st.trip_id JOIN routes r ON r.route_id = t.route_id
           WHERE st.stop_id = ? ORDER BY r.short_name""", (stop_id,))]


def active_alerts(conn, now, stop_id=None):
    params, where = [now.isoformat(), now.isoformat()], ""
    if stop_id:
        where = """AND a.alert_id IN (
            SELECT ae.alert_id FROM alert_entities ae WHERE ae.stop_id = ? OR ae.route_id IN (
                SELECT DISTINCT t.route_id FROM stop_times st JOIN trips t ON t.trip_id = st.trip_id
                WHERE st.stop_id = ?))"""
        params += [stop_id, stop_id]
    return [dict(r) for r in conn.execute(
        f"""SELECT a.alert_id, a.header, a.description, a.effect, a.cause, a.active_start, a.active_end
            FROM alerts a WHERE a.active = 1
              AND (a.active_start IS NULL OR a.active_start <= ?)
              AND (a.active_end IS NULL OR a.active_end >= ?) {where}""", params)]


def upcoming_arrivals(conn, stop_id, now, limit=6, accessible_only=False):
    """UI-3: next arrivals at a stop, merging the schedule with recorded live predictions.

    UI-5: with accessible_only, trips not marked wheelchair accessible are left out.
    """
    status = feed_status(conn, now)
    service_date = now.date()
    now_secs = timeutil.secs_since_midnight(now, service_date)
    service_ids = timeutil.active_service_ids(conn, service_date)
    if not service_ids:
        return {"live": status["live"], "arrivals": []}
    marks = ",".join("?" * len(service_ids))
    access_clause = f"AND {accessibility.trip_sql('t')}" if accessible_only else ""
    rows = conn.execute(
        f"""SELECT st.trip_id, st.arrival_secs, t.headsign, t.wheelchair_accessible, r.route_id, r.short_name,
                   tu.predicted_arrival, tu.delay_seconds, tu.cancelled, tu.recorded_at
            FROM stop_times st
            JOIN trips t ON t.trip_id = st.trip_id
            JOIN routes r ON r.route_id = t.route_id
            LEFT JOIN trip_updates tu ON tu.trip_id = st.trip_id AND tu.stop_id = st.stop_id
                 AND tu.service_date = ?
            WHERE st.stop_id = ? AND t.service_id IN ({marks})
              AND st.arrival_secs BETWEEN ? AND ? {access_clause}
            ORDER BY st.arrival_secs""",
        (service_date.isoformat(), stop_id, *service_ids, now_secs - 30 * 60, now_secs + 90 * 60),
    )
    fresh_after = now - timedelta(seconds=config.STALE_AFTER_SECONDS)
    arrivals = []
    for row in rows:
        scheduled = timeutil.scheduled_datetime(service_date, row["arrival_secs"])
        has_live = (status["live"] and row["recorded_at"] is not None
                    and datetime.fromisoformat(row["recorded_at"]) >= fresh_after)
        cancelled = bool(has_live and row["cancelled"])
        predicted = (datetime.fromisoformat(row["predicted_arrival"])
                     if has_live and row["predicted_arrival"] else None)
        expected = predicted or scheduled
        if expected < now - timedelta(minutes=1) and not cancelled:
            continue
        if cancelled and scheduled < now - timedelta(minutes=1):
            continue
        delay = row["delay_seconds"] if predicted else None
        arrivals.append({
            "trip_id": row["trip_id"],
            "route_id": row["route_id"],
            "route": row["short_name"],
            "headsign": row["headsign"],
            "scheduled": scheduled.isoformat(),
            "expected": None if cancelled else expected.isoformat(),
            "minutes_away": None if cancelled else max(0, round((expected - now).total_seconds() / 60)),
            "delay_seconds": delay,
            "status": "Cancelled" if cancelled else (delays.classify(delay) if delay is not None else "Scheduled"),
            "label": delays.status_label(delay, cancelled),
            "is_live": bool(predicted) or cancelled,
            "accessible": accessibility.is_accessible(row["wheelchair_accessible"]),
            "accessibility": accessibility.trip_label(row["wheelchair_accessible"]),
        })
        if len(arrivals) >= limit:
            break
    return {"live": status["live"], "arrivals": arrivals}


def create_app(db_path=None, now_fn=None):
    app = Flask(__name__, static_folder=str(config.BASE_DIR / "static"), static_url_path="/static")
    app.config["DB_PATH"] = db_path or config.DB_PATH
    now = now_fn or timeutil.now_local

    def conn():
        if "conn" not in g:
            g.conn = db.connect(app.config["DB_PATH"])
        return g.conn

    @app.teardown_appcontext
    def _close(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        return jsonify(feed_status(conn(), now()))

    @app.get("/api/filters")
    def filters():
        return jsonify({
            "days": [{"key": k, "label": label} for k, label, _ in delays.DAY_OF_WEEK],
            "times": [{"key": k, "label": label} for k, label, _, _ in delays.TIME_OF_DAY],
            "on_time_window": {"early_seconds": delays.ON_TIME_EARLIEST_SECONDS,
                               "late_seconds": delays.ON_TIME_LATEST_SECONDS},
        })

    @app.get("/api/stops")
    def stops():
        q = request.args.get("q", "").strip().lower()
        accessible_only = accessibility.wants_accessible(request.args.get("accessible"))
        lat, lon = DEFAULT_LOCATION
        result = []
        for s in conn().execute("SELECT * FROM stops ORDER BY stop_name"):
            routes = stop_routes(conn(), s["stop_id"])
            route_names = [(r["short_name"] or "").lower() for r in routes]
            if q and not (q in s["stop_name"].lower()
                          or (s["stop_code"] or "").startswith(q)
                          or q in route_names):
                continue
            if accessible_only and not accessibility.is_accessible(s["wheelchair_boarding"]):
                continue
            result.append({**dict(s), "accessible": accessibility.is_accessible(s["wheelchair_boarding"]),
                           "accessibility": accessibility.stop_label(s["wheelchair_boarding"]),
                           "routes": [r["short_name"] for r in routes],
                           "distance_m": _distance_m(lat, lon, s["lat"], s["lon"])})
        result.sort(key=lambda s: s["distance_m"])
        return jsonify({"you_are_here": {"lat": lat, "lon": lon}, "stops": result})

    def _stop_or_404(stop_id):
        row = conn().execute("SELECT * FROM stops WHERE stop_id = ?", (stop_id,)).fetchone()
        if row is None:
            abort(404, description="Stop not found")
        return row

    @app.get("/api/stops/<stop_id>")
    def stop_detail(stop_id):
        s = _stop_or_404(stop_id)
        return jsonify({**dict(s), "accessible": accessibility.is_accessible(s["wheelchair_boarding"]),
                        "accessibility": accessibility.stop_label(s["wheelchair_boarding"]),
                        "routes": stop_routes(conn(), stop_id),
                        "alerts": active_alerts(conn(), now(), stop_id)})

    @app.get("/api/stops/<stop_id>/arrivals")
    def arrivals(stop_id):
        s = _stop_or_404(stop_id)
        t = now()
        accessible_only = accessibility.wants_accessible(request.args.get("accessible"))
        data = upcoming_arrivals(conn(), stop_id, t, limit=int(request.args.get("limit", 6)),
                                 accessible_only=accessible_only)
        data["updated_at"] = t.isoformat()
        data["accessible_only"] = accessible_only
        if accessible_only and not accessibility.is_accessible(s["wheelchair_boarding"]):
            data["accessibility_notice"] = (
                f"This stop is marked \"{accessibility.stop_label(s['wheelchair_boarding'])}\". "
                "Showing accessible buses only.")
        data["alerts"] = active_alerts(conn(), t, stop_id)
        if not data["live"]:
            data["notice"] = "Live data is unavailable right now. Showing scheduled times only."
        return jsonify(data)

    @app.get("/api/stops/<stop_id>/reliability")
    def stop_reliability(stop_id):
        _stop_or_404(stop_id)
        try:
            return jsonify(reliability.stop_reliability(
                conn(), stop_id, request.args.get("day", "all"), request.args.get("time", "all"),
                accessibility.wants_accessible(request.args.get("accessible"))))
        except ValueError as exc:
            abort(400, description=str(exc))

    @app.get("/api/routes/<route_id>/reliability")
    def route_reliability(route_id):
        if conn().execute("SELECT 1 FROM routes WHERE route_id = ?", (route_id,)).fetchone() is None:
            abort(404, description="Route not found")
        try:
            return jsonify(reliability.route_reliability(
                conn(), route_id, request.args.get("day", "all"), request.args.get("time", "all"),
                accessibility.wants_accessible(request.args.get("accessible"))))
        except ValueError as exc:
            abort(400, description=str(exc))

    @app.get("/api/stops/<stop_id>/transfer-options")
    def stop_transfer_options(stop_id):
        _stop_or_404(stop_id)
        return jsonify(transfers.transfer_options(conn(), stop_id))

    @app.get("/api/stops/<stop_id>/transfer")
    def stop_transfer(stop_id):
        _stop_or_404(stop_id)
        args = request.args
        if not args.get("from") or not args.get("to"):
            abort(400, description="Choose the route you arrive on and the route you want to catch.")
        # No buffer (or "auto") lets transfer_risk pick a typical transfer time for the rider.
        buffer_min = args.get("buffer", "auto")
        if buffer_min == "auto":
            buffer_min = None
        else:
            try:
                buffer_min = float(buffer_min)
            except ValueError:
                abort(400, description="Transfer time must be a number of minutes.")
            if buffer_min.is_integer():
                buffer_min = int(buffer_min)
        try:
            return jsonify(transfers.transfer_risk(
                conn(), stop_id, args["from"], args["to"],
                from_headsign=args.get("from_headsign") or None,
                to_headsign=args.get("to_headsign") or None,
                buffer_min=buffer_min, day=args.get("day", "all"), time_of_day=args.get("time", "all"),
                accessible_only="accessible" in args and accessibility.wants_accessible(args["accessible"])))
        except ValueError as exc:
            abort(400, description=str(exc))

    @app.get("/api/alerts")
    def alerts():
        return jsonify(active_alerts(conn(), now(), request.args.get("stop_id")))

    @app.errorhandler(400)
    @app.errorhandler(404)
    def _json_error(err):
        return jsonify({"error": err.description}), err.code

    return app
