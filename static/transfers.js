// UI-4b: Transfer check screen.
//
// Loaded after app.js, so it can use app.js helpers: $, el, getJSON, state.
//
// Backend (UI-4a, see docs/sprint2.md):
//   GET /api/stops/<stop_id>/transfer-options
//       -> {"arrive": [{route_id, route, headsign, label}, ...], "leave": [...]}
//   GET /api/stops/<stop_id>/transfer?from=&from_headsign=&to=&to_headsign=&buffer=&day=&time=&accessible=
//       -> {made_pct, verdict, made, missed, connections, limited_data,
//           avg_planned_gap_min, avg_extra_wait_min, advice, ...}
//       -> 400 {"error": "..."} for bad choices (e.g. same route twice)

let transfersReady = false;  // the stop and filter lists only need filling once

// Fill the stop list and day/time filters (first time only), preselect `stopId`,
// then load that stop's route options.
async function initTransfers(stopId) {
  if (!transfersReady) {
    const [stopData, filters] = await Promise.all([getJSON("/api/stops"), getJSON("/api/filters")]);
    const stops = [...stopData.stops].sort((a, b) => a.stop_name.localeCompare(b.stop_name));
    $("transfer-stop").replaceChildren(...stops.map((s) =>
      el("option", { value: s.stop_id }, s.stop_name)));
    const fill = (select, items) => select.replaceChildren(
      el("option", { value: "all" }, "All"),
      ...items.map((i) => el("option", { value: i.key }, i.label)));
    fill($("transfer-day"), filters.days);
    fill($("transfer-time"), filters.times);
    transfersReady = true;
  }
  if (stopId) $("transfer-stop").value = stopId;
  $("transfer-result").hidden = true;
  await loadTransferOptions($("transfer-stop").value);
}

// Fill "I arrive on" and "And want to catch" for the chosen stop.
// Each option's value holds both route_id and headsign as JSON.
async function loadTransferOptions(stopId) {
  const result = $("transfer-result");
  try {
    const data = await getJSON(`/api/stops/${encodeURIComponent(stopId)}/transfer-options`);
    const fill = (select, options) => select.replaceChildren(...options.map((o) =>
      el("option", { value: JSON.stringify([o.route_id, o.headsign]) }, o.label)));
    fill($("transfer-from"), data.arrive);
    fill($("transfer-to"), data.leave);
    // Start with two different choices so the first check is a real transfer.
    if (data.leave.length > 1 && $("transfer-to").value === $("transfer-from").value) {
      $("transfer-to").selectedIndex = 1;
    }
  } catch (e) {
    $("transfer-from").replaceChildren();
    $("transfer-to").replaceChildren();
    result.replaceChildren(el("p", {}, "Could not load the routes for this stop."));
    result.hidden = false;
  }
}

// Run the check with the form's choices and show the result (or the API's error).
async function checkTransfer(event) {
  event.preventDefault();
  const result = $("transfer-result");
  if (!$("transfer-from").value || !$("transfer-to").value) return;
  const [from, fromHeadsign] = JSON.parse($("transfer-from").value);
  const [to, toHeadsign] = JSON.parse($("transfer-to").value);
  const params = new URLSearchParams({
    from, from_headsign: fromHeadsign, to, to_headsign: toHeadsign,
    buffer: $("transfer-buffer").value, day: $("transfer-day").value, time: $("transfer-time").value,
  });
  if (state.accessibleOnly) params.set("accessible", "1");
  result.replaceChildren(el("p", { class: "muted" }, "Checking..."));
  result.hidden = false;
  try {
    const res = await fetch(`/api/stops/${encodeURIComponent($("transfer-stop").value)}/transfer?${params}`);
    const data = await res.json();
    if (!res.ok) {
      result.replaceChildren(el("p", {}, data.error || "Could not check this transfer."));
      return;
    }
    renderTransferResult(data);
  } catch (e) {
    result.replaceChildren(el("p", {}, "Could not check this transfer. Try again."));
  }
}

// Result card: big %, the verdict in words, counts, waits and the advice line.
function renderTransferResult(r) {
  const result = $("transfer-result");
  const minutes = (m) => `${Math.round(m)} min`;
  const rows = [
    ["Recorded connections", String(r.connections)],
    ["Planned time between buses", r.avg_planned_gap_min != null ? minutes(r.avg_planned_gap_min) : null],
    ["Extra wait when missed", r.avg_extra_wait_min != null ? minutes(r.avg_extra_wait_min) : null],
  ].filter(([, value]) => value != null);
  result.replaceChildren(
    el("div", { class: "big" }, r.made_pct != null ? `${r.made_pct}%` : "–"),
    el("div", { class: "verdict" }, r.verdict),
    el("p", { class: "small" }, r.connections
      ? `Made ${r.made} of ${r.connections} recorded connections${r.accessible_only ? " (accessible buses only)" : ""}.`
      : "No recorded connections match these choices."),
    el("dl", {}, ...rows.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])),
    el("p", {}, r.advice));
  if (r.limited_data && r.connections) {
    result.append(el("p", { class: "muted small" },
      "Only a few recorded trips match. Treat this as a rough estimate."));
  }
  result.hidden = false;
}

function wireTransfers() {
  $("transfer-stop").addEventListener("change", () => {
    $("transfer-result").hidden = true;
    loadTransferOptions($("transfer-stop").value);
  });
  $("transfer-form").addEventListener("submit", checkTransfer);
  // "Check a transfer from here" on the stop screen: open with that stop selected.
  // The tab bar button: open with the last stop viewed, or the first stop.
  document.querySelectorAll('[data-tab="transfers"]').forEach((button) =>
    button.addEventListener("click", () => initTransfers(state.currentStop)));
}

wireTransfers();