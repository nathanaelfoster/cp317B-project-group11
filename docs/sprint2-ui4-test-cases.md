# Sprint 2: UI-4 Transfer risk test cases

**Story:** UI-4 Show transfer risk (5 pts, Medium). UI-4a backend: Arham Zaidi. UI-4b frontend: Gursimran Deol, built by Nathanael Foster and reworked by Arham Zaidi.
**Acceptance criterion (backlog):** given two routes and a stop, the system shows the % of past trips where the transfer would have been made.
**Setup:** branch `feature/ui-4-transfer-backend` (PR #5), sample data (`python run.py --reset`), tested on November 13, 2026.

## Manual test cases

| ID | What is tested | Steps | Expected | Actual | Result |
|----|----------------|-------|----------|--------|--------|
| TC-UI4-01 | Acceptance criterion: % of past transfers made | Transfers screen, stop University Ave. / King St., I'm on **7 to Fairway Station**, I want to catch **201 to Conestoga** | A % made and a verdict in words | "Risky connection", about 7 in 10 times (72% of 2,474 recorded connections) | Pass |
| TC-UI4-02 | Opening from a stop | Stop screen for University Ave. / King St. → **Check a transfer from here** | Form opens with that stop selected, only routes that serve it, and two different routes preselected | Stop preselected; options 201 and 7 (both directions); default pair is 201 → 7, not the same bus turning around | Pass |
| TC-UI4-03 | Changing the transfer time changes the result | TC-UI4-01, then **Change time to switch buses** → 3 minutes | Result updates without pressing the button, and the % changes | Updated to "You'll usually make it", about 9 in 10 (88%); note reads "We'll allow 3 min" | Pass |
| TC-UI4-04 | Automatic transfer time | TC-UI4-01 with transfer time left on **Automatic** | 2 minutes used and shown to the rider | "We'll allow 2 min to switch buses"; result says "We allowed 2 min" | Pass |
| TC-UI4-05 | Accessible buses only | TC-UI4-01, tick **Accessible buses only** | Only accessible trips on both legs; automatic time becomes 4 min | Needs Ito's UI-5a (`trip_sql`, `wants_accessible`). Automated tests pass with `trip_sql` stubbed in | Pending UI-5a |
| TC-UI4-06 | Same bus picked twice | I'm on 7 to Fairway Station, I want to catch 7 to Fairway Station | Plain error, no result | "Pick two different buses: the one you're on and the one you want to catch." (API: 400) | Pass |
| TC-UI4-07 | Route that doesn't serve the stop | `GET /api/stops/UNIV_KING/transfer?from=7&to=9` | 400 with a clear message | 400 "Route 9 does not leave from this stop." | Pass |
| TC-UI4-08 | Transfer time out of range | `...&buffer=16` | 400 | 400 "Transfer time must be between 0 and 15 minutes." | Pass |
| TC-UI4-09 | Missing or invalid input | `?from=7` (no `to`); `...&buffer=abc` | 400 for both | 400 "Choose the route you arrive on and the route you want to catch."; 400 "Transfer time must be a number of minutes." | Pass |
| TC-UI4-10 | Unknown stop | `GET /api/stops/NOPE/transfer?from=7&to=201` | 404 | 404 "Stop not found" | Pass |
| TC-UI4-11 | Day and time filters (reuses UI-1) | TC-UI4-01, **More options** → Weekdays, PM peak | Fewer connections counted; result can change | 465 connections (was 2,474), 68%, still "Risky" | Pass |
| TC-UI4-12 | Reliable transfer | Stop Waterloo Public Square, **301 to Conestoga** → **9 to Lakeshore** | Above 90%, "Very likely", no tip | "You'll almost always make it" (98%); no tip shown | Pass |
| TC-UI4-13 | What happens if you miss it | TC-UI4-01 | Wait for the next bus and how often it comes | "If you miss it, the next 201 to Conestoga comes about 18 min later." "The 201 usually comes every 15 min here." | Pass |
| TC-UI4-14 | Safer transfer tip | TC-UI4-01 | A tip with a transfer time that reaches the next verdict | "Tip: plan on a 201 that leaves at least 3 min after you arrive, and you'd make it about 9 in 10 times." | Pass |
| TC-UI4-15 | Exact numbers available | TC-UI4-01 → **See the numbers** | %, times made, planned gap, extra wait, cancelled trips | 72%, 1,771 of 2,474, 9 min, 18 min, 58 cancelled | Pass |
| TC-UI4-16 | Accessibility (NFR) | Inspect the result card | Verdict in words and icon, not colour alone; dot meter readable by screen readers; result in a live region | Words + icon in every verdict; meter has `role="img"` and "7 out of 10"; `aria-live="polite"` on the result | Pass |
| TC-UI4-17 | Phone screen | Viewport 375 × 812 | No sideways scrolling; everything readable | Page width 375 px, no overflow | Pass |

## Automated tests

| File | What it covers | Result |
|------|----------------|--------|
| `tests/test_transfers.py` (acceptance, 27) | Made/missed counting on hand-made history, waits, limited data, day/time/accessible filters, any direction, verdicts, options, invalid input, both endpoints | 26 pass, 1 needs UI-5a (`test_accessible_filter_applies_to_both_legs`) |
| `tests/test_transfers_extra.py` (9) | Automatic transfer time, bus frequency, safer tip, `buffer=auto` | 8 pass, 1 skipped until UI-5a |
| Both, with UI-5a's `trip_sql` stubbed in | Everything above | 36 of 36 pass |

Command: `python -m pytest tests/test_transfers.py tests/test_transfers_extra.py -v`

## Summary
16 of 17 manual cases pass. TC-UI4-05 (accessible buses only) is pending Ito's UI-5a, and needs no UI-4 changes once it lands. Re-run TC-UI4-05 and the full pytest suite on `main` after both PRs are merged.
