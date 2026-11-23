# Sprint 3 Guide

> Finish the last three rider and analyst features on top of the Sprint 1 and 2 data pipeline: live arrivals with service alerts (UI-3), barrier reporting with logins (UI-6), and analyst reports on accessible-route reliability and barrier reports (REP-4). Integrate them with the existing map, accessibility filters and transfer check, and test the whole system end to end so it is ready for the final demo.

How it builds on Sprint 2: REP-4 reuses the UI-5a accessible-trip filter and the REP-1 on-time rule, and UI-6 barrier reports feed REP-4. UI-3 finishes the live-arrivals screen that Sprint 1 started.

## Who does what

| Task | What | Owner |
|---|---|---|
| UI-6a | Logins + barrier report backend | **Itohan** |
| UI-3a | Live arrival status + fix alerts URL | **Arham** |
| REP-4a | Analyst report endpoints | **Arham** |
| UI-3b | Show live status on stop screen | **Gursimran** |
| UI-6b | Login, Report tab, admin report list | **Gursimran** |
| REP-4b | Analyst tab | **Gursimran** |

## Dependencies

- Itohan's UI-6a → Gursimran's UI-6b and Arham's REP-4a report parts
- Arham's UI-3a → Gursimran's UI-3b
- Arham's REP-4a → Gursimran's REP-4b
- Gursimran can build screens early with fake data, then plug in the real API

## Sprint 3 Deliverables

**Itohan (UI-6a)**
- [ ] Add `users`, `barrier_reports`, `report_status_history` tables
- [ ] Register / login / logout / me, with hashed passwords
- [ ] `role_required` check (rider, analyst, admin) and 3 demo accounts
- [ ] Submit a report, rate limit (3 per stop per hour, 10 per day)
- [ ] Admin moves status: Open → Under Review → Resolved
- [ ] Seed ~25 demo reports for Arham's analyst reports
- [ ] Tests

** Part 1: ** 
1. **`app/schema.sql`**: add `users`, `barrier_reports` and `report_status_history` exactly as in the contract.
2. **`app/config.py`**: add `SECRET_KEY = os.environ.get("WIMI_SECRET_KEY", "dev-only-change-me")`. In `create_app()` set `app.secret_key = config.SECRET_KEY`, and `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"`.
3. **New file `app/auth.py`**:
   - `create_user(conn, username, password, role="rider")` using `werkzeug.security.generate_password_hash`.
   - `check_login(conn, username, password)` using `check_password_hash`. Returns the user dict or `None`.
   - `current_user(conn)` reads `session["user_id"]`, returns the user dict or `None`.
   - Decorators `login_required` (401) and `role_required(*roles)` (401 if logged out, 403 if wrong role). **Arham imports `role_required` for REP-4a, so keep the name.**
   - `seed_demo_users(conn)`: creates `rider_demo`, `analyst_demo`, `admin_demo` (password `demo-password`) if they don't exist.
4. **`app/api.py`**: add `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`. Validation rules are in the contract. On login, `session.clear()` then set `session["user_id"]`.
5. **`run.py`**: call `seed_demo_users()` after `--reset`.
6. Tests in **`tests/test_auth.py`** (see list below). Open the PR.


** Part 2: ** 
1. **New file `app/barriers.py`** with the logic, so `api.py` stays thin:
   - `CATEGORIES` and `STATUSES` dicts (code to label), from the contract.
   - `ALLOWED_MOVES = {"open": {"under_review"}, "under_review": {"resolved", "open"}, "resolved": set()}`.
   - `create_report(conn, stop_id, user_id, category, description, now)`: validates, checks the rate limit, inserts the report plus the first history row (`old_status` NULL, `new_status` 'open').
   - `rate_limit_wait(conn, user_id, stop_id, now)`: returns minutes to wait, or 0. **3 per user per stop in the last hour, 10 per user in the last 24 hours.** Count rows in `barrier_reports`; no extra package needed.
   - `change_status(conn, report_id, new_status, admin_id, now)`: checks `ALLOWED_MOVES`, updates `status` and `updated_at`, sets `resolved_at` when resolving (clear it if sent back to open), adds a history row.
   - `stop_reports(conn, stop_id, include_resolved, now)` and `all_reports(conn, status=None)`.
   - `to_public(row)`: builds the report object from the contract. **No username or user id.**
2. **`app/api.py`** endpoints:
   - `POST /api/stops/<stop_id>/reports` (`login_required`)
   - `GET /api/stops/<stop_id>/reports` (public)
   - `GET /api/reports` (`role_required("admin")`, adds `reported_by`)
   - `PATCH /api/reports/<id>` (`role_required("admin")`)
   - `GET /api/stops/<stop_id>`: add `"open_reports"` (count of `open` + `under_review`).
   - Use the app's `now_fn` for timestamps (like the rest of `api.py`) so tests can control time.
3. **Demo data.** Add `seed_demo_reports(conn, now)` that creates around 25 reports over the last 60 days across 6 to 8 stops, with a mix of statuses and realistic resolution times (a few hours to a few days). Call it from `run.py --reset` after the demo users. **Arham needs this for REP-4a**, so agree on it with him by Tuesday.
4. Tests in **`tests/test_barriers.py`**. Open the PR.

------------------------------------------------------------------------------------
**Arham (UI-3a, then REP-4a)**
- [ ] Fix the alerts URL in `config.py`, (https://webapps.regionofwaterloo.ca/api/grt-routes/)

** For 3a ** 
1. **New file `app/live.py`** with:
   - `arrival_status(delay_seconds, cancelled, has_prediction)` returning `(status, status_label)`. Reuse the REP-1 on-time rule from `app/delays.py`; don't redefine the thresholds.
   - `EFFECT_LABELS` for GTFS-Realtime alert effects (`DETOUR` "Detour", `REDUCED_SERVICE` "Reduced service", `NO_SERVICE` "No service", `SIGNIFICANT_DELAYS` "Significant delays", `STOP_MOVED` "Stop moved", anything else "Service change").
   - `detoured_routes(conn, now, stop_id)`: route ids with an active `DETOUR` alert for that route or stop (use `alerts` + `alert_entities`).
2. **`app/api.py`**:
   - In `upcoming_arrivals()`, add `status`, `status_label`, `detour` and `live` to each arrival. Keep every existing field, including the UI-5 `accessible` / `accessibility` fields.
   - In `arrivals()`, add `updated_at`, `feed_age_seconds` and `stale` from the existing `feed_status()`.
   - Add `effect_label` to each alert in `active_alerts()`.
3. **Tests in `tests/test_live.py`.**

** For 4a **
1. **New file `app/analyst.py`**:
   - `least_reliable_accessible_routes(conn, now, days=30, dow=None, time=None, limit=10, min_trips=20)`. Join `trip_updates` to `trips`, filter with `accessibility.trip_sql("t")` from UI-5a, use the existing day/time filter helpers from `app/reliability.py`, and the REP-1 on-time rule from `app/delays.py`. Skip cancelled trips in the on-time % but count them in `cancelled`. Drop routes under `min_trips`. Sort by `on_time_pct` ascending.
   - `report_hotspots(conn, now, days=90, limit=10)`: group `barrier_reports` by stop, count by status, find the most common category.
   - `resolution_time(conn, now, days=90)`: average and median hours from `created_at` to `resolved_at` for reports resolved in the window, overall and by category, plus the count still unresolved. Do the median in Python, since SQLite has no `MEDIAN`.
2. **`app/api.py`**: add the three `GET /api/analyst/...` endpoints with `@role_required("analyst", "admin")`. Validate query values (`days` 1 to 365, `limit` 1 to 50, otherwise 400).
3. **Tests in `tests/test_analyst.py`** with a small hand-made fixture whose answers you can work out on paper. Write those answers in the fixture docstring, like `tests/test_transfers.py` does.

- [ ] Each arrival gets a status: on time / late / early / cancelled / scheduled, plus a detour flag
- [ ] Arrivals include "last updated" time and a stale flag
- [ ] Analyst: least reliable accessible routes (start Monday, no dependency)
- [ ] Analyst: stops with most reports, average resolution time (after Itohan's tables)
- [ ] Analyst/admin only. Tests


------------------------------------------------------------------------------------
**Gursimran (UI-3b, UI-6b, REP-4b)**
- [ ] Stop screen: status in words, detour/cancelled tags, "Updated X s ago", stale warning
- [ ] Login in the Profile tab
- [ ] Report tab form (stop, category, description). Clear messages for errors and rate limit
- [ ] Barrier reports listed on the stop screen
- [ ] Admin-only "Manage reports" list with status buttons
- [ ] Analyst tab (analysts/admins only) with 3 tables
- [ ] Status shown as text, works with keyboard


** UI-3b ** 
**Steps** (`static/app.js`, `static/index.html`, `static/styles.css`)
1. In the arrivals list, show `status_label` next to each time (e.g. "Late 6 min"). Add a CSS class per `status` for colour, but the words must be there.
2. Cancelled arrivals: strike through the time and show "Cancelled". `detour: true`: add a "Detour" tag. `live: false`: show "Scheduled" in muted text.
3. Under the stop name, show "Updated 12 s ago" from `feed_age_seconds`, and tick it up each second between refreshes.
4. When `stale` is true, show a banner: "Live data is delayed. Times may be out of date."
5. Show `effect_label` in each alert box heading (e.g. "Detour: Route 7 ...").
6. Put the arrivals list in an `aria-live="polite"` region so screen readers hear updates.
7. Confirm the 30 s refresh still stops when you leave the stop screen (existing `stopRefresh()`).

** UI-6b ** 
**Steps**
1. **Login / sign-up.** Add a login section to the **Profile** tab (it already exists from UI-5b): username, password, "Log in" and "Create account" buttons. When logged in, show "Logged in as sam (rider)" and "Log out". Call `GET /api/auth/me` on page load and keep the user in `state.user`. Put the shared code in a new `static/auth.js`.
2. **Report tab.** Replace the placeholder with a form:
   - Stop picker (search by name, reuse the map's stop list). When the rider taps "Report a barrier at this stop" on the stop screen, open the Report tab with that stop already chosen.
   - Category `<select>` with the labels from the contract.
   - Description `<textarea>` with a "123 / 500" counter.
   - Submit calls `POST /api/stops/<id>/reports`.
   - Logged out: show "Log in to report a barrier" with a button to the Profile tab instead of the form.
3. **Error messages** (show them in text above the button, and move focus there):
   - 400: show the server's `error`.
   - 401: "Your session ended. Please log in again."
   - 429: "You've sent several reports recently. Try again in N minutes." (N = `retry_after_minutes`)
4. **Success:** "Thanks! Your report is Open." and clear the form.
5. **Stop screen:** show a "Barrier reports (2)" section using `open_reports` and `GET /api/stops/<id>/reports`: category label, short description, status label, and date. Add a "Show resolved" toggle (`include_resolved=1`).
6. **Admin view** (only when `state.user.role === "admin"`): on the Report tab, a "Manage reports" list from `GET /api/reports` with a status filter. Each report has buttons for its allowed next steps only ("Start review", "Mark resolved", "Send back to open") calling `PATCH /api/reports/<id>`. We need this to demo Open → Under Review → Resolved.

** REP-4b **
**Steps**
1. Add an **Analyst** button to the tab bar that only appears when `state.user.role` is `analyst` or `admin`. Hide it again on logout.
2. New `static/analyst.js` and an Analyst screen with three sections:
   - **Least reliable accessible routes:** a table (route, trips measured, on-time %, average delay, cancelled). A "Look back" select (7 / 30 / 90 days) and the same Day and Time dropdowns as the reliability screen (reuse `/api/filters`).
   - **Barrier report hotspots:** a table (stop, total, open, under review, resolved, most common barrier). Clicking a stop name opens its stop screen.
   - **Report resolution time:** three numbers (average hours, median hours, still unresolved), and a small table by category. Show "No reports resolved in this period" when the values are `null`.
3. Tables are fine (and easiest to make accessible). Use `<caption>` and `<th scope="col">`. If you have time left, add a simple CSS bar in the on-time % column.
4. Show "Loading..." while fetching, and a message on 401/403 ("Analyst access only").

**Everyone:** run all tests, walk through the app together, log bugs. Test table is in `integration-testing.md`.

## API endpoints

**Itohan builds, Gursimran uses**
- `POST /api/auth/register`, `/login`, `/logout`, `GET /api/auth/me`
- `POST /api/stops/<id>/reports` (logged in)
- `GET /api/stops/<id>/reports` (anyone)
- `GET /api/reports`, `PATCH /api/reports/<id>` (admin)

**Arham builds, Gursimran uses**
- `GET /api/stops/<id>/arrivals` (existing, add status fields)
- `GET /api/analyst/accessible-routes`
- `GET /api/analyst/report-hotspots`
- `GET /api/analyst/resolution-time`

Exact fields and error codes: `api-contract.md`.
