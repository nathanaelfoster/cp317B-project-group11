"""UI-4: Transfer risk.

"If I ride route A to this stop and plan to catch route B, how often would I
actually have made it?"

How the calculation works:
  1. Take every recorded arrival of route A at the stop from trip_updates
     (stored by REP-3, delays calculated by REP-1).
  2. For each one, find the route B trip the rider PLANNED to catch: the first
     B trip on the same service date scheduled to leave at least `buffer_min`
     minutes after A's scheduled arrival.
  3. The transfer is MADE if B actually left (scheduled + delay) at least
     `buffer_min` minutes after A actually arrived (scheduled + delay).
     A cancelled B trip counts as MISSED. Skip cancelled A trips and rows with
     no recorded delay. Skip A arrivals with no planned B trip left that day.
  4. made_pct = made / (made + missed), rounded to a whole number.
"""
from . import accessibility, delays  # noqa: F401  (you will need both)
from .reliability import MIN_TRIPS_FOR_CONFIDENCE, _filters  # noqa: F401

DEFAULT_BUFFER_MIN = 2   # time to cross the platform or the street
MAX_BUFFER_MIN = 15

# (lowest made %, verdict), checked top to bottom.
VERDICTS = [
    (90, "Very likely"),
    (75, "Likely"),
    (50, "Risky"),
    (0, "Unlikely"),
]


def verdict(made_pct) -> str:
    """Verdict word for a made percentage using VERDICTS. None -> "Not enough data".

    Examples: 95 -> "Very likely", 90 -> "Very likely", 89 -> "Likely",
    60 -> "Risky", 10 -> "Unlikely".
    """
    # TODO(UI-4a)
    raise NotImplementedError


def transfer_options(conn, stop_id) -> dict:
    """Route and direction pairs a rider can arrive on and leave on at a stop.

    Returns {"arrive": [option, ...], "leave": [option, ...]} where each option is
    {"route_id", "route" (short name), "headsign", "label"}, e.g. label "7 to Fairway Station",
    sorted by route short name then headsign.

    You cannot ARRIVE on a trip that starts at this stop (stop_sequence 1), and you
    cannot LEAVE on a trip that ends here (its last stop_sequence).
    """
    # TODO(UI-4a)
    raise NotImplementedError


def transfer_risk(conn, stop_id, from_route, to_route, from_headsign=None, to_headsign=None,
                  buffer_min=DEFAULT_BUFFER_MIN, day="all", time_of_day="all",
                  accessible_only=False) -> dict:
    """How often a planned transfer at `stop_id` from one route to another would have worked.

    - day / time_of_day filter route A's arrivals; reuse _filters() from app/reliability.py.
    - accessible_only keeps only accessible trips on BOTH legs (use accessibility.trip_sql).
    - from_headsign / to_headsign narrow a route to one direction; None means any direction.

    Raises ValueError when:
      - buffer_min is outside 0..MAX_BUFFER_MIN
      - from and to are the same route and the same direction
      - a route does not arrive (from) or leave (to) at this stop (see transfer_options)

    Returns a dict with these keys:
      stop_id, from {"route_id", "headsign"}, to {"route_id", "headsign"}, buffer_min,
      filters {"day", "time"}, accessible_only,
      connections          made + missed
      made, missed
      made_pct             whole number, None when connections == 0
      verdict              verdict(made_pct), but "Not enough data" when
                           connections < MIN_TRIPS_FOR_CONFIDENCE
      limited_data         connections < MIN_TRIPS_FOR_CONFIDENCE
      cancelled_arrivals   route A arrivals skipped because they were cancelled
      avg_planned_gap_min  average scheduled minutes between A arriving and planned B (None if none)
      avg_extra_wait_min   when missed, average extra minutes until the next B the rider
                           could actually catch (None if none)
      advice               one line for riders, e.g. "Consider taking an earlier bus, or
                           allowing more transfer time." when made_pct < 75
    """
    # TODO(UI-4a)
    raise NotImplementedError
