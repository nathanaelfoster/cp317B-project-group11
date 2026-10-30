# Sprint 1 guide: REP-1 and UI-1

Everything else in the prototype is wired up and waiting on these two pieces.
Until they are done, the collector and the arrivals screen raise
`NotImplementedError`, and the matching tests fail.

## Setup

```bash
pip install -r requirements.txt
python -m pytest tests/test_delays.py tests/test_reliability.py
```

## REP-1 Delay Calculation — `app/delays.py`

Acceptance criteria (Milestone 02):
- Delay = recorded arrival − scheduled arrival, measured in minutes.
- On time = from 1 minute early to 5 minutes late, inclusive.
- Statuses use words, not only colour.

Implement the four functions marked `TODO(REP-1)`:

1. `compute_delay_seconds(scheduled, recorded)`
2. `classify(delay_seconds)`
3. `status_label(delay_seconds, cancelled=False)`
4. `summarize(delays)`

Done when `python -m pytest tests/test_delays.py` passes.
Suggested commit: `REP-1: implement delay calculation and on-time classification`.

## UI-1 Historical Delay Display — `app/reliability.py`

Acceptance criteria:
- Riders see the average delay and on-time percentage for a stop or route.
- They can filter by day of week and time of day.

Implement `_filters(day, time_of_day)` (marked `TODO(UI-1)`). It turns
the dropdown choices into SQL conditions; `_report()` already runs the query
and calls your `summarize()`.

Done when `python -m pytest tests/test_reliability.py` passes.
Suggested commit: `UI-1: filter reliability by day of week and time of day`.

## Check it end to end

```bash
python -m pytest          # all tests should pass
python run.py --reset     # then open http://localhost:5000
```

Pick a stop, then change the Day and Time dropdowns under "Usual reliability
here". The numbers should change, and arrivals should show "Late 7 min",
"On time" and so on.

## For the Sprint 01 report

- Testing and Review: the tests in `tests/test_delays.py` map directly onto the
  REP-1 acceptance criteria (edges at −60 s and +300 s).
- Screenshots: the stop detail screen with filters set, e.g. Weekdays + PM peak.
