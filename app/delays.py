"""REP-1: Delay Calculation.

A delay is the recorded arrival time minus the scheduled arrival time, measured
in minutes. Arrivals from 1 minute early to 5 minutes late count as on time.
"""
from datetime import datetime

ON_TIME_EARLIEST_SECONDS = -60   # 1 minute early
ON_TIME_LATEST_SECONDS = 5 * 60  # 5 minutes late

# Time-of-day filters for UI-1, as (key, label, start hour inclusive, end hour exclusive).
TIME_OF_DAY = [
    ("early", "Early (before 7 AM)", 0, 7),
    ("am_peak", "AM peak (7-10 AM)", 7, 10),
    ("midday", "Midday (10 AM-3 PM)", 10, 15),
    ("pm_peak", "PM peak (3-7 PM)", 15, 19),
    ("evening", "Evening (after 7 PM)", 19, 30),  # GTFS times can pass 24:00
]

# Day-of-week filters for UI-1, as (key, label, weekday numbers with Monday = 0).
DAY_OF_WEEK = [
    ("weekday", "Weekdays", [0, 1, 2, 3, 4]),
    ("saturday", "Saturday", [5]),
    ("sunday", "Sunday", [6]),
]


def compute_delay_seconds(scheduled: datetime, recorded: datetime) -> int:
    """Recorded arrival minus scheduled arrival, in whole seconds (negative = early).

    TODO(REP-1): subtract the two datetimes and return whole seconds.
    Example: scheduled 2:10:00 PM, recorded 2:14:00 PM -> 240.
    """
    return int((recorded - scheduled).total_seconds())


def delay_minutes(delay_seconds: int) -> float:
    return round(delay_seconds / 60, 1)


def classify(delay_seconds: int) -> str:
    """Return "Early", "On time" or "Late" using the REP-1 on-time window.

    TODO(REP-1): use ON_TIME_EARLIEST_SECONDS and ON_TIME_LATEST_SECONDS.
    Both edges count as on time: -60 -> "On time", -61 -> "Early",
    300 -> "On time", 301 -> "Late".
    """
    if delay_seconds < ON_TIME_EARLIEST_SECONDS:
        return "Early"
    if delay_seconds > ON_TIME_LATEST_SECONDS:
        return "Late"
    return "On time"


def status_label(delay_seconds, cancelled=False) -> str:
    """Text label for riders. Status never relies on colour alone (accessibility NFR).

    TODO(REP-1): return
      "Cancelled"            if cancelled is True
      "Scheduled"            if delay_seconds is None (no live data)
      "On time"              if classify() says on time
      "Late 7 min" / "Early 3 min" otherwise, with minutes = round(abs(seconds) / 60),
                             never less than 1
    """
    if cancelled:
        return "Cancelled"
    if delay_seconds is None:
        return "Scheduled"
    status = classify(delay_seconds)
    if status == "On time":
        return status
    minutes = max(1, round(abs(delay_seconds) / 60))
    return f"{status} {minutes} min"


def summarize(delays: list) -> dict:
    """Average delay and on-time percentage for a list of delays in seconds.

    TODO(REP-1): return a dict with these keys:
      trips          number of delays
      on_time        how many classify() as "On time"
      on_time_pct    whole-number percentage, e.g. 75 (None when there are no trips)
      avg_delay_min  mean delay in minutes via delay_minutes() (None when no trips)
    UI-1 (app/reliability.py) uses this to build its report.
    """
    trips = len(delays)
    if trips == 0:
        return {"trips": 0, "on_time": 0, "on_time_pct": None, "avg_delay_min": None}
    on_time = sum(1 for d in delays if classify(d) == "On time")
    return {
        "trips": trips,
        "on_time": on_time,
        "on_time_pct": round(100 * on_time / trips),
        "avg_delay_min": delay_minutes(sum(delays) / trips),
    }
