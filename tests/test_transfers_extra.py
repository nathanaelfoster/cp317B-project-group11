"""UI-4 rider-friendly additions: automatic transfer time, how often the bus comes, safer tip.

Uses the hand-made `history` from test_transfers.py. Route 201 to Conestoga is
recorded on Wednesday at 8:05, 9:05, 9:20, 10:05 (cancelled) and 10:20.
"""
import pytest

from app import accessibility, transfers

from .test_transfers import A_HEAD, B_HEAD, STOP, client, history, risk  # noqa: F401  (fixtures)


def _has_trip_sql():
    try:
        accessibility.trip_sql("t")
        return True
    except NotImplementedError:
        return False


needs_ui5a = pytest.mark.skipif(not _has_trip_sql(), reason="needs UI-5a accessibility.trip_sql")


# ---------- Automatic transfer time ----------

def test_transfer_time_is_picked_for_the_rider(history):
    r = risk(history)
    assert r["buffer_auto"] is True
    assert r["buffer_min"] == transfers.DEFAULT_BUFFER_MIN == 2


def test_a_chosen_transfer_time_is_kept(history):
    r = risk(history, buffer_min=5)
    assert r["buffer_auto"] is False
    assert r["buffer_min"] == 5


@needs_ui5a
def test_accessible_riders_get_more_time(history):
    r = risk(history, accessible_only=True)
    assert r["buffer_auto"] is True
    assert r["buffer_min"] == transfers.ACCESSIBLE_BUFFER_MIN == 4


# ---------- How often the next bus comes ----------

def test_how_often_route_b_comes(history):
    # Wednesday gaps 60, 15, 45, 15 min -> median 30. Saturday has one bus, so no gap.
    assert risk(history)["to_every_min"] == 30.0


def test_no_frequency_without_two_buses(conn):
    r = transfers.transfer_risk(conn, STOP, "7", "201", from_headsign=A_HEAD, to_headsign=B_HEAD)
    assert r["to_every_min"] is None
    assert r["safer"] is None


# ---------- Safer transfer time tip ----------

def test_safer_tip_reaches_the_next_band(history):
    # 50% at 2 min. 3 and 5 min stay at 50%; at 8 min A1, A2 and A3 all connect.
    assert risk(history)["safer"] == {"buffer_min": 8, "made_pct": 100}


def test_no_tip_when_already_very_likely(history):
    assert risk(history, buffer_min=8)["safer"] is None


# ---------- API ----------

@pytest.mark.parametrize("buffer", ["&buffer=auto", ""])
def test_endpoint_accepts_automatic_buffer(client, buffer):
    res = client.get(f"/api/stops/{STOP}/transfer?from=7&from_headsign={A_HEAD}"
                     f"&to=201&to_headsign={B_HEAD}{buffer}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["buffer_auto"] is True and data["buffer_min"] == 2
    assert data["to_every_min"] == 30.0
