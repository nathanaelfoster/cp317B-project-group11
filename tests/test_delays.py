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


@pytest.mark.parametrize("seconds, expected", [
    (-60, "On time"),       # on-time edges never show minutes
    (300, "On time"),
    (0, "On time"),         # zero is a real delay, not missing data
    (301, "Late 5 min"),    # just past the window
    (-61, "Early 1 min"),
    (3600, "Late 60 min"),
    (-600, "Early 10 min"),
])
def test_label_edges_and_minutes(seconds, expected):
    assert delays.status_label(seconds) == expected


def test_cancelled_wins_over_missing_or_late_data():
    assert delays.status_label(None, cancelled=True) == "Cancelled"
    assert delays.status_label(900, cancelled=True) == "Cancelled"


def test_summarize_counts_window_edges_as_on_time():
    result = delays.summarize([-60, 300])
    assert result["on_time"] == 2
    assert result["on_time_pct"] == 100


def test_summarize_none_on_time():
    result = delays.summarize([-120, 400, 900])
    assert result["on_time"] == 0
    assert result["on_time_pct"] == 0


def test_summarize_rounds_percentage_to_whole_number():
    assert delays.summarize([0, 600, 900])["on_time_pct"] == 33   # 1 of 3
    assert delays.summarize([0, 60, 900])["on_time_pct"] == 67    # 2 of 3


def test_summarize_single_trip():
    assert delays.summarize([420]) == {"trips": 1, "on_time": 0, "on_time_pct": 0, "avg_delay_min": 7.0}


def test_summarize_average_can_be_early_and_is_rounded():
    assert delays.summarize([-120, -60])["avg_delay_min"] == -1.5
    assert delays.summarize([100])["avg_delay_min"] == 1.7   # 100 s = 1.67 min


def test_summarize_does_not_change_the_input():
    data = [0, 600]
    delays.summarize(data)
    assert data == [0, 600]
