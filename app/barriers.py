"""UI-6a: barrier reports riders submit for a stop, and their review status.

All the rules live here so app/api.py stays thin. Public report objects never
include who reported them (Location Privacy / rider privacy).
"""
import math
from datetime import datetime, timedelta

CATEGORIES = {
    "ramp": "Broken ramp",
    "elevator": "Elevator out of service",
    "snow_ice": "Snow or ice",
    "sidewalk": "Blocked sidewalk",
    "shelter": "Damaged shelter",
    "other": "Other",
}

STATUSES = {
    "open": "Open",
    "under_review": "Under review",
    "resolved": "Resolved",
}

# Open -> Under review -> Resolved, and an admin can send a report back to open.
ALLOWED_MOVES = {"open": {"under_review"}, "under_review": {"resolved", "open"}, "resolved": set()}

MAX_DESCRIPTION = 500

# Rate limit: per user, at most 3 reports per stop per hour and 10 reports per day.
PER_STOP_LIMIT, PER_STOP_WINDOW = 3, timedelta(hours=1)
PER_DAY_LIMIT, PER_DAY_WINDOW = 10, timedelta(hours=24)

# include_resolved shows resolved reports from this far back.
RESOLVED_LOOKBACK = timedelta(days=30)

_REPORT_SELECT = """SELECT br.*, s.stop_name, u.username
                    FROM barrier_reports br
                    JOIN stops s ON s.stop_id = br.stop_id
                    JOIN users u ON u.id = br.user_id"""


class ReportError(ValueError):
    """Bad input for a report (400)."""


class RateLimited(Exception):
    """Too many reports recently (429)."""

    def __init__(self, retry_after_minutes):
        super().__init__(f"Rate limited for {retry_after_minutes} min")
        self.retry_after_minutes = retry_after_minutes


def _parse(value):
    return datetime.fromisoformat(value) if value else None


def validate(category, description):
    """Return the cleaned description, or raise ReportError."""
    if category not in CATEGORIES:
        raise ReportError("Choose a barrier type from the list.")
    if not isinstance(description, str) or not description.strip():
        raise ReportError("Describe the barrier in a few words.")
    description = description.strip()
    if len(description) > MAX_DESCRIPTION:
        raise ReportError(f"Keep the description to {MAX_DESCRIPTION} characters or fewer.")
    return description


def _minutes_until_free(times, limit, window, now):
    """times: report datetimes inside the window, oldest first. 0 when under the limit."""
    if len(times) < limit:
        return 0
    # The report that has to age out so the user drops back under the limit.
    frees_at = times[len(times) - limit] + window
    return max(1, math.ceil((frees_at - now).total_seconds() / 60))


def rate_limit_wait(conn, user_id, stop_id, now):
    """Minutes the user must wait before reporting at this stop, or 0."""
    # Coarse string filter first (offsets can differ by an hour across DST),
    # then an exact check on the parsed times.
    rows = conn.execute(
        "SELECT stop_id, created_at FROM barrier_reports WHERE user_id = ? AND created_at >= ?",
        (user_id, (now - PER_DAY_WINDOW - timedelta(days=1)).isoformat()))
    recent = [(r["stop_id"], _parse(r["created_at"])) for r in rows]
    day = sorted(t for _, t in recent if now - t < PER_DAY_WINDOW)
    here = sorted(t for s, t in recent if s == stop_id and now - t < PER_STOP_WINDOW)
    return max(_minutes_until_free(here, PER_STOP_LIMIT, PER_STOP_WINDOW, now),
               _minutes_until_free(day, PER_DAY_LIMIT, PER_DAY_WINDOW, now))


def create_report(conn, stop_id, user_id, category, description, now):
    """Validate, check the rate limit, and save a new open report. Returns the public report."""
    description = validate(category, description)
    if conn.execute("SELECT 1 FROM stops WHERE stop_id = ?", (stop_id,)).fetchone() is None:
        raise LookupError("Stop not found")
    wait = rate_limit_wait(conn, user_id, stop_id, now)
    if wait:
        raise RateLimited(wait)
    stamp = now.isoformat()
    cur = conn.execute(
        """INSERT INTO barrier_reports (stop_id, user_id, category, description, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'open', ?, ?)""",
        (stop_id, user_id, category, description, stamp, stamp))
    conn.execute(
        """INSERT INTO report_status_history (report_id, old_status, new_status, changed_by, changed_at)
           VALUES (?, NULL, 'open', ?, ?)""",
        (cur.lastrowid, user_id, stamp))
    conn.commit()
    return to_public(get_report(conn, cur.lastrowid))


def get_report(conn, report_id):
    """The full report row (including username, for admin use), or None."""
    return conn.execute(f"{_REPORT_SELECT} WHERE br.id = ?", (report_id,)).fetchone()


def to_public(row):
    """The report object from the API contract. No username or user id."""
    return {
        "id": row["id"],
        "stop_id": row["stop_id"],
        "stop_name": row["stop_name"],
        "category": row["category"],
        "category_label": CATEGORIES[row["category"]],
        "description": row["description"],
        "status": row["status"],
        "status_label": STATUSES[row["status"]],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "resolved_at": row["resolved_at"],
    }


def _newest_first(rows):
    return sorted(rows, key=lambda r: (_parse(r["created_at"]), r["id"]), reverse=True)


def stop_reports(conn, stop_id, include_resolved, now):
    """Open and under-review reports at a stop, newest first.

    With include_resolved, also reports resolved in the last 30 days.
    """
    rows = conn.execute(f"{_REPORT_SELECT} WHERE br.stop_id = ?", (stop_id,)).fetchall()
    keep = []
    for r in rows:
        if r["status"] != "resolved":
            keep.append(r)
        elif include_resolved and r["resolved_at"] and now - _parse(r["resolved_at"]) <= RESOLVED_LOOKBACK:
            keep.append(r)
    return [to_public(r) for r in _newest_first(keep)]


class InvalidMove(Exception):
    """A status change ALLOWED_MOVES doesn't permit (409)."""

    def __init__(self, old_status, new_status):
        super().__init__(f"Can't move a report from {old_status} to {new_status}")
        self.allowed = sorted(ALLOWED_MOVES.get(old_status, ()))


def change_status(conn, report_id, new_status, admin_id, now):
    """Move a report to new_status and record it in the history. Returns the full row.

    Raises LookupError for an unknown report, ReportError for an unknown status,
    and InvalidMove when the move isn't allowed.
    """
    row = get_report(conn, report_id)
    if row is None:
        raise LookupError("Report not found")
    if new_status not in STATUSES:
        raise ReportError("Status must be open, under_review or resolved.")
    old_status = row["status"]
    if new_status not in ALLOWED_MOVES[old_status]:
        raise InvalidMove(old_status, new_status)
    stamp = now.isoformat()
    # Resolving stamps resolved_at; sending a report back to open clears it.
    resolved_at = stamp if new_status == "resolved" else None
    conn.execute(
        "UPDATE barrier_reports SET status = ?, updated_at = ?, resolved_at = ? WHERE id = ?",
        (new_status, stamp, resolved_at, report_id))
    conn.execute(
        """INSERT INTO report_status_history (report_id, old_status, new_status, changed_by, changed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (report_id, old_status, new_status, admin_id, stamp))
    conn.commit()
    return get_report(conn, report_id)


def all_reports(conn, status=None):
    """Every report (optionally one status), newest first, with reported_by for admins."""
    if status is not None and status not in STATUSES:
        raise ReportError("Status must be open, under_review or resolved.")
    if status:
        rows = conn.execute(f"{_REPORT_SELECT} WHERE br.status = ?", (status,)).fetchall()
    else:
        rows = conn.execute(_REPORT_SELECT).fetchall()
    return [to_admin(r) for r in _newest_first(rows)]


def to_admin(row):
    """The public report plus who reported it. Admin responses only."""
    return {**to_public(row), "reported_by": row["username"]}


def open_report_count(conn, stop_id):
    """Reports at a stop that still need attention (open or under review)."""
    return conn.execute(
        "SELECT COUNT(*) FROM barrier_reports WHERE stop_id = ? AND status IN ('open', 'under_review')",
        (stop_id,)).fetchone()[0]
