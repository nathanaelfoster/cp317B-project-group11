# Sprint 2 guide: UI-5 Accessibility filters and UI-4 Transfer risk

Sprint 2 is due **Friday, November 13, 2026 at 11:59 PM**. REP-1 and REP-3 are
already done. This sprint adds two rider features on top of them:

| Task | Story | Ideal hours |
|------|-------|-------------|
| UI-5a Accessibility filters: backend | UI-5 (3 pts, High) | 5.5 |
| UI-5b Accessibility filters: frontend | UI-5 | 5.5 |
| UI-4a Transfer risk: backend | UI-4 (5 pts, Medium) | 9.5 |
| UI-4b Transfer risk: frontend | UI-4 | 6 |
| Testing and review, REP-3 alerts fix | All | ~10 |

**Order matters:** UI-5a first, then UI-4a, which reuses the UI-5a filter.
The frontend tasks can start on layout right away, but they need their
backend task merged before they show real data.

## What's already on main

Like Sprint 1, the new files are committed as a skeleton: function headers,
docstrings that say exactly what each function must do, and `TODO(...)` tags
where your code goes. The acceptance tests are already written.

| File | Task | What it is |
|------|------|------------|
| `app/accessibility.py` | UI-5a | The accessibility rules: what counts as accessible, text labels, reading `?accessible=`, a SQL helper. Every function raises `NotImplementedError`. |
| `app/transfers.py` | UI-4a | `verdict()`, `transfer_options()` and `transfer_risk()`. The module docstring explains the calculation. |
| `tests/test_accessibility.py` | UI-5a | Acceptance tests for UI-5. Don't change them. Make them pass. |
| `tests/test_transfers.py` | UI-4a | Acceptance tests for UI-4. The fixture docstring lists each hand-made case and its expected answer. |
| `static/profile.js` | UI-5b | Stubs for the shared accessible toggle and the optional profile. |
| `static/transfers.js` | UI-4b | Stubs for the Transfer check screen. |

To find every spot for your task: `grep -rn "TODO(UI-5a)" app static tests`.
Use your own tag in place of `UI-5a`.

You will also **edit some existing files** (`app/api.py`, `app/reliability.py`,
`tools/make_sample_gtfs.py`, `static/index.html`, `static/app.js`). Each task
below lists exactly where.

## Setup

```bash
git checkout main && git pull
pip install -r requirements.txt
python -m pytest              # 54 pass, 50 fail: the failures are the Sprint 2 work
python run.py --reset         # http://localhost:5000
```

Work on your own branch, open a pull request into `main`, and have one
teammate review it. Suggested branch names are listed under each task.

---

## UI-5a Accessibility filters: backend

Branch: `feature/ui-5-accessible-backend`

Acceptance criteria (backlog): *turning the filter on hides stops and trips not
marked wheelchair-accessible.*

GTFS already gives us what we need, and Sprint 1 stores it in `app/schema.sql`:
`stops.wheelchair_boarding` and `trips.wheelchair_accessible`. Both use
0 = no information, 1 = accessible and 2 = not accessible. **Only 1 counts as
accessible.** Treat 0 as not accessible, so a rider never sees an option they
might not be able to use.

**Start here: `app/accessibility.py`.** Fill in the five functions. Their
docstrings give the exact inputs and outputs. The first five tests in
`tests/test_accessibility.py` check them.

**Then edit these existing files:**

1. **`app/api.py`**
   - Add `accessibility` to the `from . import ...` line at the top.
   - `stops()`: replace the Sprint 1 check
     (`request.args.get("accessible") in ("1", "true")` and
     `s["wheelchair_boarding"] != 1`) with `accessibility.wants_accessible()`
     and `accessibility.is_accessible()`. Add an `"accessibility"` text label
     (`accessibility.stop_label()`) to each stop.
   - `stop_detail()`: add the same `"accessibility"` label.
   - `upcoming_arrivals()`: add an `accessible_only=False` parameter. When it's
     on, add `accessibility.trip_sql("t")` to the SQL `WHERE`. Also select
     `t.wheelchair_accessible` and add `"accessible"` (true/false) and
     `"accessibility"` (`accessibility.trip_label()`) to every arrival.
   - `arrivals()`: read `?accessible=`, pass it to `upcoming_arrivals()`, and
     add `"accessible_only"` to the response. If the filter is on and the stop
     itself isn't accessible, add an `"accessibility_notice"` string telling
     the rider.
   - `stop_reliability()` and `route_reliability()` endpoints: pass
     `accessible_only=accessibility.wants_accessible(request.args.get("accessible"))`.
2. **`app/reliability.py`**: give `_report()`, `stop_reliability()` and
   `route_reliability()` an `accessible_only=False` parameter. When it's on,
   `JOIN trips t ON t.trip_id = tu.trip_id` and add `accessibility.trip_sql("t")`
   to the clauses. Add `"accessible_only"` to the returned dict.
3. **`tools/make_sample_gtfs.py`, then regenerate the data.** Right now every
   sample trip is accessible, so the filter has nothing to hide in the demo.
   Where trips are built (`trips.append(...)`, last value `1`), mark some as 2:
   for example, every third Route 7 trip and every other Route 9 trip, as
   "older buses". In `STOPS`, set `PHILLIP_COLUMBIA`'s last value to 0
   (unknown). Then run `python tools/make_sample_gtfs.py` and
   `python run.py --reset`. The tests set their own flags, so they pass
   either way. This step is for the demo.

Done when `python -m pytest tests/test_accessibility.py` passes, and the
Sprint 1 tests still pass.
Suggested commit: `UI-5: filter stops, arrivals and reliability to accessible trips`.

---

## UI-5b Accessibility filters: frontend

Branch: `feature/ui-5-accessible-frontend`

**Start here: `static/profile.js`.** Fill in `setAccessibleOnly()`,
`loadProfile()`, `saveProfile()`, `clearProfile()` and `initProfile()`. The
comment above each one says what it does. The rule is **one shared
setting**, `state.accessibleOnly`. Every checkbox marked
`data-accessible-toggle` shows it and changes it.

**Then edit these existing files:**

1. **`static/index.html`**
   - At the bottom, load the new file after `app.js`:
     `<script src="/static/profile.js"></script>`
   - Map screen: change the checkbox to
     `<input id="accessible-only" type="checkbox" data-accessible-toggle> Accessible stops and buses only`,
     and add `<p id="profile-note" class="muted small" hidden>Turned on by your accessibility profile.</p>` under it.
   - Stop screen, just above `<p id="arrivals-notice" ...>`: add a checkbox
     `<input id="stop-accessible-only" type="checkbox" data-accessible-toggle> Accessible buses only`
     (inside a `<label class="checkbox small">`), and
     `<p id="accessibility-notice" class="notice" hidden></p>`.
   - Profile screen: replace the "Coming in a later sprint" paragraph with:
     a line saying the profile is optional and saved only on this device, and
     a `<form id="profile-form">` holding a checkbox
     `id="profile-accessible"` ("I need wheelchair-accessible stops and
     buses"), a Save submit button, and a Clear button `id="profile-clear"`
     (`type="button"`). Under the form, add
     `<p id="profile-status" class="notice" role="status" hidden></p>`.
2. **`static/app.js`**
   - Add `accessibleOnly: false` to the `state` object at the top.
   - `loadStops()`: use `state.accessibleOnly` instead of reading
     `#accessible-only` directly. Remove the old `change` listener on
     `#accessible-only`, because `profile.js` wires all the toggles now.
   - `loadArrivals()` and `loadReliability()`: add `accessible=1` to the URL
     when `state.accessibleOnly` is on. In `loadArrivals()`, show
     `data.accessibility_notice` in `#accessibility-notice`. Under each arrival,
     add `a.accessibility` **as text**, for example a
     `<span class="trip-access">`. Colour can be added, but it must not be the
     only signal (accessibility NFR).
3. **`static/styles.css`** (optional): style `.trip-access` (small, muted)
   and the profile form.

Done when these manual checks pass (after UI-5a is merged and the sample data
is regenerated):
- Map: turning the checkbox on removes Albert St. / Seagram Dr. and
  Phillip St. / Columbia St.
- Stop screen for Waterloo Public Square: turning the filter on removes some
  Route 7 and Route 9 arrivals, and every arrival says "Accessible bus".
- Turning it on in one place turns it on everywhere.
- Save the profile and reload: the filter is still on. Clear it and reload:
  it's off.

Suggested commit: `UI-5: accessible toggles and optional accessibility profile`.

---

## UI-4a Transfer risk: backend

Branch: `feature/ui-4-transfer-backend` (start after UI-5a is merged)

Acceptance criteria (backlog): *given two routes and a stop, the system shows
the % of past trips where the transfer would have been made.*

**Start here: `app/transfers.py`.** The module docstring explains the
calculation in four steps. In short: for every recorded arrival of route A,
find the route B trip the rider planned to catch, then use the REP-1 delays
to check whether B actually left after A actually arrived plus the buffer.
Fill in, in this order:

1. `verdict()`: the easy one. `test_verdicts` checks it.
2. `transfer_options()`: which route and direction pairs a rider can arrive on
   and leave on at a stop. Look at `stop_routes()` in `app/api.py` for a
   similar query.
3. `transfer_risk()`: the calculation. The docstring lists every key it must
   return and every case that raises `ValueError`. Reuse `_filters()` from
   `app/reliability.py` for day and time, and `accessibility.trip_sql()` for
   the accessible filter.

Tip: work through the five cases in the `history` fixture docstring in
`tests/test_transfers.py` by hand first. The tests expect exactly those answers.

**Then edit `app/api.py`:** add `transfers` to the imports and add two
endpoints just above `/api/alerts`:
- `GET /api/stops/<stop_id>/transfer-options` returns
  `transfers.transfer_options()` as JSON.
- `GET /api/stops/<stop_id>/transfer` takes the query parameters `from`,
  `from_headsign`, `to`, `to_headsign`, `buffer` (default 2), `day`, `time`
  and `accessible`.
- Both use `_stop_or_404()`. Return 400 (`abort(400, description=...)`) when
  `from` or `to` is missing, `buffer` isn't a number, or `transfer_risk()`
  raises `ValueError`. The existing error handler turns that into
  `{"error": "..."}`.

Done when `python -m pytest tests/test_transfers.py` passes.
Suggested commit: `UI-4: calculate transfer success rate from recorded delays`.

Sanity check with the regenerated sample data: Route 7 to Fairway Station,
then Route 201 to Conestoga at University Ave. / King St. with a 2-minute
buffer, should come out around 70% ("Risky"). ION 301 to Route 9 at Waterloo
Public Square should be above 90%.

---

## UI-4b Transfer risk: frontend

Branch: `feature/ui-4-transfer-frontend`

**Start here: `static/transfers.js`.** Fill in `initTransfers()`,
`loadTransferOptions()`, `checkTransfer()`, `renderTransferResult()` and
`wireTransfers()`. The header comment shows exactly what the two endpoints
return.

**Then edit `static/index.html`:**
- At the bottom, load the new file after `app.js`:
  `<script src="/static/transfers.js"></script>`
- Replace the "Coming in Sprint 2" paragraph on the Transfers screen with a
  `<form id="transfer-form">` containing:
  - `<select id="transfer-stop">` Transfer stop
  - `<select id="transfer-from">` I arrive on
  - `<select id="transfer-to">` And want to catch
  - `<select id="transfer-buffer">` Time I need to get between buses, with
    options 0, 1, 2 (selected), 3, 5, 8 and 10 minutes
  - `<select id="transfer-day">` and `<select id="transfer-time">` (copy the
    `.filters` layout from the stop screen)
  - `<input id="transfer-accessible-only" type="checkbox" data-accessible-toggle>` Accessible buses only
  - a submit button: "Check this transfer"
- Under the form, add `<div id="transfer-result" class="result" aria-live="polite" hidden></div>`.

**Optional, `static/styles.css`:** style `.result` as a bordered card with a
big percentage.

Done when these manual checks pass (after UI-4a is merged):
- From University Ave. / King St., "Check a transfer from here" opens the
  form with that stop selected and the right route options.
- 7 to Fairway Station, then 201 to Conestoga, 2 min: shows a % and a verdict.
  Changing to 5 min changes the result.
- Picking the same route and direction twice shows the error message.

Suggested commit: `UI-4: transfer check screen with result card`.

---

## Testing and review, REP-3 alerts fix

1. **REP-3 alerts feed fix: `app/config.py`.** `GRT_ALERTS_URL` currently
   reads the `GRT_TRIP_UPDATES_URL` environment variable and defaults to a
   trip-updates URL, so in live mode no alerts ever show. Point it at the GRT
   alerts feed (check the URL on the Region of Waterloo open data portal),
   read `GRT_ALERTS_URL`, and add the missing newline at the end of the file.
   Suggested commit: `REP-3: fix alerts feed URL and setting name`.
2. **Test plan and results.** For UI-5 and UI-4, write one test case per
   acceptance criterion plus the edge cases above (ID, steps, expected,
   actual, pass/fail). Run them once both features are merged.
3. **Automated run.** Run `python -m pytest -v` on `main` after the merges,
   and save the output for the report.
4. **Review.** Review at least one backend and one frontend pull request.

---

## Check it end to end

```bash
python -m pytest              # everything passes
python run.py --reset
```

Demo flow for the video (1-3 minutes):
1. Map: turn on "Accessible stops and buses only". Inaccessible stops disappear.
2. Open Waterloo Public Square. Inaccessible buses are hidden, and each
   arrival says "Accessible bus".
3. Profile: save the setting, reload, and the filter is still on.
4. "Check a transfer from here" at University Ave. / King St.: run 7, then
   201. Change the buffer and show the % change.
5. Briefly show `python -m pytest` passing.

## For the Sprint 02 report

- **Implementation Progress:** screenshots of the map with the filter on, the
  stop screen with accessible labels, the Profile screen, and the Transfer
  result card. A short snippet of `transfer_risk()` shows the integration
  with REP-1.
- **Integration:** UI-4 reads delays stored by REP-3 and calculated by REP-1,
  and reuses the UI-5 accessible filter and the UI-1 day/time filters.
- **Testing and Review:** the test case table, plus the pytest output.
