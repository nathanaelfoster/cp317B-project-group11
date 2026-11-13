// UI-4b: Transfer check screen.
//
// Loaded after app.js (add <script src="/static/transfers.js"></script> below app.js in
// index.html), so it can use app.js helpers: $, el, getJSON, state.
//
// Backend (UI-4a, see docs/sprint2.md):
//   GET /api/stops/<stop_id>/transfer-options
//       -> {"arrive": [{route_id, route, headsign, label}, ...], "leave": [...]}
//   GET /api/stops/<stop_id>/transfer?from=&from_headsign=&to=&to_headsign=&buffer=&day=&time=&accessible=
//       -> {made_pct, verdict, made, missed, connections, limited_data,
//           avg_planned_gap_min, avg_extra_wait_min, advice, ...}
//       -> 400 {"error": "..."} for bad choices (e.g. same route twice)

// Fill #transfer-stop with every stop, alphabetical (GET /api/stops gives the list),
// and #transfer-day / #transfer-time with the same choices as the reliability filters
// (GET /api/filters). Preselect `stopId` if given, then call loadTransferOptions().
async function initTransfers(stopId) {
  // TODO(UI-4b)
}

// GET /api/stops/<stopId>/transfer-options. Fill #transfer-from with data.arrive and
// #transfer-to with data.leave, showing each option's label ("7 to Fairway Station").
// Each <option> value must carry BOTH route_id and headsign, e.g. JSON.stringify([route_id, headsign]).
async function loadTransferOptions(stopId) {
  // TODO(UI-4b)
}

// Submit handler for #transfer-form.
// Build the query from the form (from, from_headsign, to, to_headsign, buffer, day, time)
// plus accessible=1 when state.accessibleOnly is on. Call the transfer endpoint, then
// renderTransferResult(). On a 400, show the response's "error" text in #transfer-result.
async function checkTransfer(event) {
  event.preventDefault();
  // TODO(UI-4b)
}

// Show the result in #transfer-result (unhide it):
// - made_pct big ("73%"), then the verdict ("Risky")
// - "Made X of Y recorded connections"
// - average planned gap, and average extra wait when missed (skip if null)
// - the advice line
// - if limited_data: "Only a few recorded trips match. Treat this as a rough estimate."
// Use text, not colour alone, for the verdict (accessibility NFR).
function renderTransferResult(result) {
  // TODO(UI-4b)
}

// Run once on page load:
// - #transfer-stop change -> loadTransferOptions(new stop)
// - #transfer-form submit -> checkTransfer
// - the stop screen's "Check a transfer from here" button (data-tab="transfers" inside
//   #screen-stop) should open Transfers with state.currentStop preselected: initTransfers(state.currentStop)
// - otherwise initTransfers() when the Transfers tab is opened the first time
function wireTransfers() {
  // TODO(UI-4b)
}

wireTransfers();
