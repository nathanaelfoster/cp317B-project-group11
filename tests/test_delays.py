"""REP-1 Delay Calculation acceptance tests."""
from datetime import datetime, timedelta

import pytest

from app import delays, timeutil

SCHEDULED = datetime(2026, 10, 28, 14, 10, tzinfo=timeutil.TZ)


def at(seconds):
    return SCHEDULED + timedelta(seconds=seconds)


def test_delay_is_recorded_minus_scheduled():
    assert delays.compute_delay_seconds(SCHEDULED, at(240)) == 240
    assert delays.compute_delay_seconds(SCHEDULED, at(-90)) == -90
    assert delays.compute_delay_seconds(SCHEDULED, SCHEDULED) == 0


def test_delay_is_reported_in_minutes():
    assert delays.delay_minutes(240) == 4.0
    assert delays.delay_minutes(-90) == -1.5


@pytest.mark.parametrize("seconds, expected", [
    (-61, "Early"),
    (-60, "On time"),   # exactly 1 minute early is on time
    (0, "On time"),
    (300, "On time"),   # exactly 5 minutes late is on time
    (301, "Late"),
    (900, "Late"),
])
def test_on_time_window_is_one_minute_early_to_five_late(seconds, expected):
    assert delays.classify(seconds) == expected


def test_labels_use_words_not_just_colour():
    assert delays.status_label(240) == "On time"
    assert delays.status_label(420) == "Late 7 min"
    assert delays.status_label(-170) == "Early 3 min"
    assert delays.status_label(None) == "Scheduled"
    assert delays.status_label(120, cancelled=True) == "Cancelled"


def test_summarize_average_and_on_time_percentage():
    result = delays.summarize([0, 60, 600, -60])  # 3 of 4 on time
    assert result["trips"] == 4
    assert result["on_time"] == 3
    assert result["on_time_pct"] == 75
    assert result["avg_delay_min"] == 2.5  # (0 + 60 + 600 - 60) / 4 = 150 s


def test_summarize_with_no_data():
    assert delays.summarize([]) == {"trips": 0, "on_time": 0, "on_time_pct": None, "avg_delay_min": None}
