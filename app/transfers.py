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
from . import accessibility, delays
from .reliability import MIN_TRIPS_FOR_CONFIDENCE, _filters

DEFAULT_BUFFER_MIN = 2   # time to cross the platform or the street
ACCESSIBLE_BUFFER_MIN = 4  # extra time for ramps, kneeling buses and boarding
MAX_BUFFER_MIN = 15
BUFFER_CHOICES = (3, 5, 8, 10)  # larger transfer times to try for the "safer" tip

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
    if made_pct is None:
        return "Not enough data"
    # VERDICTS runs from the highest band down, so the first band we reach is the right one.
    for lowest, word in VERDICTS:
        if made_pct >= lowest:
            return word
    return VERDICTS[-1][1]


def transfer_options(conn, stop_id) -> dict:
    """Route and direction pairs a rider can arrive on and leave on at a stop.

    Returns {"arrive": [option, ...], "leave": [option, ...]} where each option is
    {"route_id", "route" (short name), "headsign", "label"}, e.g. label "7 to Fairway Station",
    sorted by route short name then headsign.

    You cannot ARRIVE on a trip that starts at this stop (stop_sequence 1), and you
    cannot LEAVE on a trip that ends here (its last stop_sequence).
    """
    # For every trip that stops here, compare this stop's position with the trip's
    # first and last stops. A route and direction counts if at least one of its trips
    # passes through rather than starting (arrive) or ending (leave) here.
    rows = conn.execute(
        """SELECT t.route_id, r.short_name AS route, t.headsign,
                  MAX(st.stop_sequence > ends.first_seq) AS can_arrive,
                  MAX(st.stop_sequence < ends.last_seq) AS can_leave
           FROM stop_times st
           JOIN trips t ON t.trip_id = st.trip_id
           JOIN routes r ON r.route_id = t.route_id
           JOIN (SELECT trip_id, MIN(stop_sequence) AS first_seq, MAX(stop_sequence) AS last_seq
                 FROM stop_times
                 WHERE trip_id IN (SELECT trip_id FROM stop_times WHERE stop_id = ?)
                 GROUP BY trip_id) ends ON ends.trip_id = st.trip_id
           WHERE st.stop_id = ?
           GROUP BY t.route_id, r.short_name, t.headsign
           ORDER BY r.short_name, t.headsign""", (stop_id, stop_id))

    options = {"arrive": [], "leave": []}
    for row in rows:
        label = f"{row['route']} to {row['headsign']}" if row["headsign"] else row["route"]
        option = {"route_id": row["route_id"], "route": row["route"],
                  "headsign": row["headsign"], "label": label}
        if row["can_arrive"]:
            options["arrive"].append(option)
        if row["can_leave"]:
            options["leave"].append(option)
    return options


def _serves(options, route_id, headsign):
    """True if one of the options is this route (and this direction, when one is given)."""
    return any(o["route_id"] == route_id and (headsign is None or o["headsign"] == headsign)
               for o in options)


def _recorded(conn, stop_id, route_id, headsign, accessible_only, clauses=(), params=()):
    """Recorded rows for one route at the stop, oldest first. `clauses` use the tu alias."""
    where = ["tu.stop_id = ?", "tu.route_id = ?"]
    args = [stop_id, route_id]
    if headsign is not None:
        where.append("t.headsign = ?")
        args.append(headsign)
    if accessible_only:
        where.append(accessibility.trip_sql("t"))
    return conn.execute(
        f"""SELECT tu.service_date, tu.scheduled_secs, tu.delay_seconds, tu.cancelled
            FROM trip_updates tu JOIN trips t ON t.trip_id = tu.trip_id
            WHERE {' AND '.join(where + list(clauses))}
            ORDER BY tu.service_date, tu.scheduled_secs""", [*args, *params]).fetchall()


def _advice(made_pct, connections):
    if connections == 0:
        return "No recorded connections match this transfer yet."
    if made_pct >= 90:
        line = "This connection is usually made."
    elif made_pct >= 75:
        line = "This connection is usually made, but allow a little extra time when you can."
    else:
        line = "Consider taking an earlier bus, or allowing more transfer time."
    if connections < MIN_TRIPS_FOR_CONFIDENCE:
        line = f"Based on only {connections} recorded connections, so treat this as a rough guide. {line}"
    return line


def transfer_risk(conn, stop_id, from_route, to_route, from_headsign=None, to_headsign=None,
                  buffer_min=None, day="all", time_of_day="all",
                  accessible_only=False) -> dict:
    """How often a planned transfer at `stop_id` from one route to another would have worked.

    - day / time_of_day filter route A's arrivals; reuse _filters() from app/reliability.py.
    - accessible_only keeps only accessible trips on BOTH legs (use accessibility.trip_sql).
    - from_headsign / to_headsign narrow a route to one direction; None means any direction.
    - buffer_min None picks a typical transfer time for the rider: DEFAULT_BUFFER_MIN, or
      ACCESSIBLE_BUFFER_MIN when accessible_only is on.

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
      buffer_auto          True when buffer_min was picked for the rider
      to_every_min         typical minutes between route B buses here (median, None if unknown)
      safer                {"buffer_min", "made_pct"}: the smallest larger transfer time from
                           BUFFER_CHOICES that reaches the next verdict band, or None
    """
    buffer_auto = buffer_min is None
    if buffer_auto:
        buffer_min = ACCESSIBLE_BUFFER_MIN if accessible_only else DEFAULT_BUFFER_MIN
    if not 0 <= buffer_min <= MAX_BUFFER_MIN:
        raise ValueError(f"Transfer time must be between 0 and {MAX_BUFFER_MIN} minutes.")
    if from_route == to_route and from_headsign == to_headsign:
        raise ValueError("Pick two different routes, or two directions of the same route.")
    options = transfer_options(conn, stop_id)
    if not _serves(options["arrive"], from_route, from_headsign):
        raise ValueError(f"Route {from_route} does not arrive at this stop.")
    if not _serves(options["leave"], to_route, to_headsign):
        raise ValueError(f"Route {to_route} does not leave from this stop.")

    # Step 1: route A arrivals, narrowed by the UI-1 day and time filters.
    clauses, params = _filters(day, time_of_day)
    arrivals = _recorded(conn, stop_id, from_route, from_headsign, accessible_only, clauses, params)

    # Route B departures by service date. A B row with no delay and no cancellation
    # has no known outcome, so it can't be used.
    departures = {}
    for b in _recorded(conn, stop_id, to_route, to_headsign, accessible_only):
        if b["cancelled"] or b["delay_seconds"] is not None:
            departures.setdefault(b["service_date"], []).append(b)

    counts = _count(arrivals, departures, round(buffer_min * 60))
    made, missed = counts["made"], counts["missed"]
    planned_gaps, extra_waits = counts["planned_gaps"], counts["extra_waits"]

    # Step 4: the summary.
    connections = made + missed
    made_pct = round(made / connections * 100) if connections else None
    limited_data = connections < MIN_TRIPS_FOR_CONFIDENCE
    return {
        "stop_id": stop_id,
        "from": {"route_id": from_route, "headsign": from_headsign},
        "to": {"route_id": to_route, "headsign": to_headsign},
        "buffer_min": buffer_min,
        "filters": {"day": day or "all", "time": time_of_day or "all"},
        "accessible_only": accessible_only,
        "connections": connections,
        "made": made,
        "missed": missed,
        "made_pct": made_pct,
        "verdict": "Not enough data" if limited_data else verdict(made_pct),
        "limited_data": limited_data,
        "cancelled_arrivals": counts["cancelled_arrivals"],
        "avg_planned_gap_min": delays.delay_minutes(sum(planned_gaps) / len(planned_gaps)) if planned_gaps else None,
        "avg_extra_wait_min": delays.delay_minutes(sum(extra_waits) / len(extra_waits)) if extra_waits else None,
        "advice": _advice(made_pct, connections),
        "buffer_auto": buffer_auto,
        "to_every_min": _typical_headway_min(departures),
        "safer": _safer(arrivals, departures, buffer_min, made_pct),
    }


def _count(arrivals, departures, buffer_secs):
    """Steps 2 and 3 for one transfer time: made, missed, skipped cancellations and waits."""
    made = missed = cancelled_arrivals = 0
    planned_gaps, extra_waits = [], []

    for a in arrivals:
        if a["cancelled"]:
            cancelled_arrivals += 1
            continue
        if a["delay_seconds"] is None:
            continue
        a_actual = a["scheduled_secs"] + a["delay_seconds"]
        same_day = departures.get(a["service_date"], [])

        # Step 2: the B the rider planned on, from the timetable alone.
        planned_i = next((i for i, b in enumerate(same_day)
                          if b["scheduled_secs"] >= a["scheduled_secs"] + buffer_secs), None)
        if planned_i is None:
            continue
        planned = same_day[planned_i]
        planned_gaps.append(planned["scheduled_secs"] - a["scheduled_secs"])

        # Step 3: did B actually leave late enough for the rider to make it?
        def catchable(b):
            return not b["cancelled"] and b["scheduled_secs"] + b["delay_seconds"] >= a_actual + buffer_secs

        if catchable(planned):
            made += 1
            continue
        missed += 1
        caught = next((b for b in same_day[planned_i + 1:] if catchable(b)), None)
        if caught is not None:
            extra_waits.append(caught["scheduled_secs"] + caught["delay_seconds"] - planned["scheduled_secs"])

    return {"made": made, "missed": missed, "cancelled_arrivals": cancelled_arrivals,
            "planned_gaps": planned_gaps, "extra_waits": extra_waits}


def _typical_headway_min(departures):
    """Median scheduled minutes between one route B bus and the next on the same day.

    The median keeps a long overnight gap from making a frequent route look rare.
    """
    gaps = sorted(later["scheduled_secs"] - earlier["scheduled_secs"]
                  for day in departures.values()
                  for earlier, later in zip(day, day[1:])
                  if later["scheduled_secs"] > earlier["scheduled_secs"])
    if not gaps:
        return None
    mid = len(gaps) // 2
    median = gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2
    return delays.delay_minutes(median)


def _safer(arrivals, departures, buffer_min, made_pct):
    """The smallest larger transfer time that lifts the result into the next verdict band."""
    if made_pct is None or made_pct >= VERDICTS[0][0]:
        return None
    # The lowest made % of the next band up, e.g. 72 ("Risky") needs 75 ("Likely").
    target = min(lowest for lowest, _ in VERDICTS if lowest > made_pct)
    for choice in BUFFER_CHOICES:
        if choice <= buffer_min:
            continue
        counts = _count(arrivals, departures, choice * 60)
        connections = counts["made"] + counts["missed"]
        if connections and round(counts["made"] / connections * 100) >= target:
            return {"buffer_min": choice, "made_pct": round(counts["made"] / connections * 100)}
    return None
