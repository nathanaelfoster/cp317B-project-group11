"""UI-5: Accessibility filters.

GTFS marks every stop (stops.wheelchair_boarding) and every trip
(trips.wheelchair_accessible) with:
    0 = no information, 1 = accessible, 2 = not accessible.

Only 1 counts as accessible. "No information" is treated as NOT accessible, so
the filter never shows a rider an option they might not be able to use.

Used by app/api.py (stops, arrivals), app/reliability.py and app/transfers.py.
"""

UNKNOWN, ACCESSIBLE, NOT_ACCESSIBLE = 0, 1, 2

STOP_LABELS = {
    ACCESSIBLE: "Accessible stop",
    NOT_ACCESSIBLE: "Not wheelchair accessible",
    UNKNOWN: "Accessibility unknown",
}
TRIP_LABELS = {
    ACCESSIBLE: "Accessible bus",
    NOT_ACCESSIBLE: "Not wheelchair accessible",
    UNKNOWN: "Accessibility unknown",
}


def wants_accessible(value) -> bool:
    """Read the ?accessible= query value.

    "1", "true", "yes" and "on" (any case, surrounding spaces ignored) -> True.
    Anything else, including None and "" -> False.
    """
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def is_accessible(flag) -> bool:
    """True only when GTFS explicitly marks the stop or trip as accessible (flag == 1)."""
    return flag == ACCESSIBLE


def stop_label(flag) -> str:
    """Text label for a stop from STOP_LABELS. Unexpected values use the UNKNOWN label."""
    return STOP_LABELS.get(flag, STOP_LABELS[UNKNOWN])


def trip_label(flag) -> str:
    """Text label for a trip from TRIP_LABELS. Unexpected values use the UNKNOWN label."""
    return TRIP_LABELS.get(flag, TRIP_LABELS[UNKNOWN])


def trip_sql(alias="t") -> str:
    """SQL condition that keeps only accessible trips, for a query that joins trips AS <alias>.

    Example: trip_sql("t") -> "t.wheelchair_accessible = 1"
    """
    return f"{alias}.wheelchair_accessible = {ACCESSIBLE}"
