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

    Example: scheduled 2:10:00 PM, recorded 2:14:00 PM -> 240 (4 minutes late).
    """
    # Subtracting two datetimes gives a timedelta (a length of time).
    # .total_seconds() turns that into a number like 240.0, and int() drops the
    # decimal so we get whole seconds. A positive answer means the bus was late,
    # a negative answer means it was early.
    return int((recorded - scheduled).total_seconds())


def delay_minutes(delay_seconds: int) -> float:
    """Convert seconds to minutes, rounded to one decimal place (e.g. 90 -> 1.5)."""
    return round(delay_seconds / 60, 1)


def classify(delay_seconds: int) -> str:
    """Return "Early", "On time" or "Late" using the REP-1 on-time window.

    Both edges count as on time: -60 -> "On time", -61 -> "Early",
    300 -> "On time", 301 -> "Late".
    """
    # More than 1 minute early (e.g. -61 seconds or lower) -> Early.
    if delay_seconds < ON_TIME_EARLIEST_SECONDS:
        return "Early"

    # More than 5 minutes late (e.g. 301 seconds or higher) -> Late.
    if delay_seconds > ON_TIME_LATEST_SECONDS:
        return "Late"

    # Anything left is between -60 and 300 seconds, edges included -> On time.
    # We use < and > (not <= and >=) above so that exactly -60 and exactly 300
    # fall through to here.
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
    raise NotImplementedError("REP-1: status_label")


def summarize(delays: list) -> dict:
    """Average delay and on-time percentage for a list of delays in seconds.

    TODO(REP-1): return a dict with these keys:
      trips          number of delays
      on_time        how many classify() as "On time"
      on_time_pct    whole-number percentage, e.g. 75 (None when there are no trips)
      avg_delay_min  mean delay in minutes via delay_minutes() (None when no trips)
    UI-1 (app/reliability.py) uses this to build its report.
    """
    raise NotImplementedError("REP-1: summarize")
