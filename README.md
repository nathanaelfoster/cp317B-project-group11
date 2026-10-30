# Will I Make It?

A transit reliability prototype for Grand River Transit (GRT) riders, built by
CP317B Group 11. It collects GRT's live GTFS-Realtime data, compares it with the
published schedule, and shows riders how reliable a stop or route really is.

**Team:** Nathanael Foster, Itohan Odigie, Arham Zaidi, Gursimran Deol

## Sprint 1 scope

| Story | What it covers | Where |
|-------|----------------|-------|
| REP-2 Transit Data Storage | GTFS schedule, wheelchair info, recorded trip updates linked to trip + stop + date | `app/schema.sql`, `app/gtfs_loader.py` |
| REP-3 Automated Data Collection | Polls GTFS-Realtime every 30 s, stores trip updates and alerts, logs every attempt | `app/collector.py` |
| REP-1 Delay Calculation | Delay = recorded − scheduled; on time = 1 min early to 5 min late | `app/delays.py` |
| UI-1 Historical Delay Display | Average delay and on-time % for a stop or route, filtered by day and time | `app/reliability.py` |
| UI-2 Interactive Transit Map | Map of stops, search, accessible-only filter, nearby list | `static/` |
| UI-3 Live Arrivals and Alerts | Next arrivals with Late / On time / Cancelled labels and alerts, refreshed every 30 s | `app/api.py`, `static/app.js` |

Deferred to later sprints: transfer check, barrier reports, accessibility
profiles, analyst reports, sign-in.

## Running it

Needs Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Open http://localhost:5000. The first start builds `data/wimi.sqlite3`, loads
the sample schedule and seeds four weeks of sample history. Use
`python run.py --reset` to rebuild it.

### Sample mode vs live mode

By default the app runs in **sample mode**: a small made-up schedule around
Waterloo (`data/sample_gtfs/`) and a simulated realtime feed, so it works
offline and gives repeatable demos. The page shows a "Demo mode" banner.

To use real GRT data:

```bash
WIMI_MODE=live python run.py --reset
```

Check the feed URLs in `app/config.py` against the Region of Waterloo open data
portal first; override them with `GRT_STATIC_URL`, `GRT_TRIP_UPDATES_URL` and
`GRT_ALERTS_URL` if they have moved. Live mode has no history at first; it
builds up as the collector runs.

## Tests

```bash
python -m pytest
```

Tests are grouped by story: `test_delays.py` (REP-1), `test_reliability.py`
(UI-1), `test_gtfs_loader.py` (REP-2), `test_collector.py` (REP-3) and
`test_api.py` (UI-2, UI-3).

## How it fits together

```
GRT GTFS zip ──> gtfs_loader ──┐
                                ├──> SQLite (stops, trips, stop_times, trip_updates, alerts, collection_log)
GRT GTFS-RT ──> collector (30s)┘                │
                                                 ▼
                         delays + reliability ─> Flask API (/api/...) ─> static/ (map + stop screens)
```

API endpoints:

- `GET /api/stops?q=&accessible=1` stops for the map and list
- `GET /api/stops/<id>` stop details, routes and active alerts
- `GET /api/stops/<id>/arrivals` next arrivals, live where available
- `GET /api/stops/<id>/reliability?day=weekday&time=pm_peak` history for a stop
- `GET /api/routes/<id>/reliability?...` history for a route
- `GET /api/status` collector health and success rate over 24 hours

## Requirements traceability

- **Accessibility (WCAG 2.1 AA):** statuses are text ("Late 7 min"), not just
  colour; keyboard-focusable controls; labelled inputs; screen-reader live
  regions for arrivals.
- **Data reliability:** every collection is logged in `collection_log`; if the
  last success is over 90 s old, riders see "Live data is unavailable" and
  scheduled times rather than stale predictions.
- **Location privacy:** the app never asks for the rider's location; distances
  use a fixed point near University Ave. / King St.
- **Fairness of estimates:** reliability is labelled as an estimate and flagged
  "Limited data" below 10 recorded arrivals.

## Contributing

Work on a branch, run `python -m pytest` before pushing, and open a pull
request. Write commit messages that name the story, e.g.
`REP-1: classify arrivals as early, on time or late`.
