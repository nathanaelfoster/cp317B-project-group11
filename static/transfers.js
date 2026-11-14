// UI-4b: Transfer check screen.
//
// Loaded after app.js, so it can use app.js helpers: $, el, getJSON, state.
//
// Backend (UI-4a, see docs/sprint2.md):
//   GET /api/stops/<stop_id>/transfer-options
//       -> {"arrive": [{route_id, route, headsign, label}, ...], "leave": [...]}
//   GET /api/stops/<stop_id>/transfer?from=&from_headsign=&to=&to_headsign=&buffer=&day=&time=&accessible=
//       buffer=auto (or left out) lets the server pick a typical time to switch buses.
//       -> {made_pct, verdict, made, missed, connections, limited_data, buffer_min, buffer_auto,
//           avg_planned_gap_min, avg_extra_wait_min, to_every_min, safer, advice, ...}
//       -> 400 {"error": "..."} for bad choices (e.g. same route twice)

let transfersReady = false;  // the stop and filter lists only need filling once
let checkSeq = 0;            // only the newest check may draw the result

// Typical time to switch buses when the rider leaves it on Automatic (matches app/transfers.py).
const AUTO_BUFFER_MIN = { standard: 2, accessible: 4 };

// How each verdict reads to a rider. The icon is decoration; the words carry the meaning.
const VERDICT_TEXT = {
  "Very likely": { cls: "v-very", icon: "✅", title: "You'll almost always make it" },
  "Likely": { cls: "v-likely", icon: "👍", title: "You'll usually make it" },
  "Risky": { cls: "v-risky", icon: "⚠️", title: "Risky connection" },
  "Unlikely": { cls: "v-unlikely", icon: "✖", title: "You'll often miss it" },
  "Not enough data": { cls: "v-none", icon: "ℹ️", title: "Not enough trips yet" },
};

// Fill the stop list and day/time filters (first time only), preselect `stopId`,
// then load that stop's route options and show a result straight away.
async function initTransfers(stopId) {
  if (!transfersReady) {
    const [stopData, filters] = await Promise.all([getJSON("/api/stops"), getJSON("/api/filters")]);
    const stops = [...stopData.stops].sort((a, b) => a.stop_name.localeCompare(b.stop_name));
    $("transfer-stop").replaceChildren(...stops.map((s) =>
      el("option", { value: s.stop_id }, s.stop_name)));
    const fill = (select, anyLabel, items) => select.replaceChildren(
      el("option", { value: "all" }, anyLabel),
      ...items.map((i) => el("option", { value: i.key }, i.label)));
    fill($("transfer-day"), "Any day", filters.days);
    fill($("transfer-time"), "Any time", filters.times);
    transfersReady = true;
  }
  if (stopId) $("transfer-stop").value = stopId;
  $("transfer-result").hidden = true;
  if (await loadTransferOptions($("transfer-stop").value)) checkTransfer();
}

// Fill "I'm on" and "I want to catch" for the chosen stop. Returns true when it worked.
// Each option's value holds both route_id and headsign as JSON.
async function loadTransferOptions(stopId) {
  const result = $("transfer-result");
  try {
    const data = await getJSON(`/api/stops/${encodeURIComponent(stopId)}/transfer-options`);
    const fill = (select, options) => select.replaceChildren(...options.map((o) =>
      el("option", { value: JSON.stringify([o.route_id, o.headsign]) }, o.label)));
    fill($("transfer-from"), data.arrive);
    fill($("transfer-to"), data.leave);
    // Start with a different route to catch, so the first check is a real transfer
    // (not the same bus turning around).
    const fromRoute = data.arrive[0]?.route_id;
    const other = data.leave.findIndex((o) => o.route_id !== fromRoute);
    if (other >= 0) $("transfer-to").selectedIndex = other;
    return data.arrive.length > 0 && data.leave.length > 0;
  } catch (e) {
    $("transfer-from").replaceChildren();
    $("transfer-to").replaceChildren();
    result.replaceChildren(el("p", {}, "Sorry, we couldn't load the buses for this stop."));
    result.hidden = false;
    return false;
  }
}

// The "We'll allow N min to switch buses" line under the form.
function updateBufferNote(minutes) {
  const choice = $("transfer-buffer").value;
  const auto = choice === "auto";
  const n = minutes ?? (auto
    ? (state.accessibleOnly ? AUTO_BUFFER_MIN.accessible : AUTO_BUFFER_MIN.standard)
    : Number(choice));
  $("transfer-buffer-note").replaceChildren(
    "We'll allow ", el("strong", {}, `${n} min`), " to switch buses",
    auto && state.accessibleOnly ? " (a little extra for boarding with accessible buses)." : ".");
}

// Run the check with the form's choices and show the result (or a plain error).
async function checkTransfer(event) {
  if (event) event.preventDefault();
  const result = $("transfer-result");
  updateBufferNote();
  if (!$("transfer-from").value || !$("transfer-to").value) return;
  if ($("transfer-from").value === $("transfer-to").value) {
    result.replaceChildren(el("p", {}, "Pick two different buses: the one you're on and the one you want to catch."));
    result.className = "result";
    result.hidden = false;
    return;
  }
  const [from, fromHeadsign] = JSON.parse($("transfer-from").value);
  const [to, toHeadsign] = JSON.parse($("transfer-to").value);
  const params = new URLSearchParams({
    from, from_headsign: fromHeadsign, to, to_headsign: toHeadsign,
    buffer: $("transfer-buffer").value, day: $("transfer-day").value, time: $("transfer-time").value,
  });
  if (state.accessibleOnly) params.set("accessible", "1");
  const seq = ++checkSeq;
  result.setAttribute("aria-busy", "true");
  if (result.hidden) {
    result.replaceChildren(el("p", { class: "muted" }, "Checking..."));
    result.hidden = false;
  }
  try {
    const res = await fetch(`/api/stops/${encodeURIComponent($("transfer-stop").value)}/transfer?${params}`);
    const data = await res.json();
    if (seq !== checkSeq) return;  // a newer check started while this one was loading
    if (!res.ok) {
      result.className = "result";
      result.replaceChildren(el("p", {}, data.error || "Sorry, we couldn't check this transfer."));
      return;
    }
    renderTransferResult(data);
  } catch (e) {
    if (seq !== checkSeq) return;
    result.className = "result";
    result.replaceChildren(el("p", {}, "Sorry, we couldn't check this transfer. Try again."));
  } finally {
    if (seq === checkSeq) result.removeAttribute("aria-busy");
  }
}

// "7 in 10" style wording for a percentage.
function inTen(pct) {
  const n = Math.round(pct / 10);
  if (n >= 10) return "almost every time";
  if (n <= 0) return "almost never";
  return `about ${n} in 10 times`;
}

// Ten dots, filled for each "in 10". Read out as one image by screen readers.
function dotMeter(pct) {
  const n = Math.min(10, Math.max(0, Math.round(pct / 10)));
  return el("div", { class: "dots", role: "img", "aria-label": `${n} out of 10` },
    ...Array.from({ length: 10 }, (_, i) => el("span", { class: i < n ? "dot on" : "dot" })));
}

// Result card: plain answer first, then what to do, with the numbers tucked away.
function renderTransferResult(r) {
  const result = $("transfer-result");
  const v = VERDICT_TEXT[r.verdict] || VERDICT_TEXT["Not enough data"];
  const toLabel = $("transfer-to").selectedOptions[0]?.textContent || "bus";
  const toRoute = toLabel.split(" to ")[0];
  const min = (m) => `${Math.round(m)} min`;
  const hasData = r.connections > 0 && r.made_pct != null;
  updateBufferNote(r.buffer_min);

  const body = [el("div", { class: "verdict-band" },
    el("span", { class: "icon", "aria-hidden": "true" }, v.icon), el("strong", {}, v.title))];

  if (hasData) {
    body.push(
      el("p", { class: "headline" }, "You'd make it ", el("strong", {}, inTen(r.made_pct)), "."),
      dotMeter(r.made_pct));
  } else {
    body.push(el("p", {}, "We don't have recorded trips for this connection yet. Try another day or time, or check back later."));
  }

  const tips = [];
  if (hasData && r.missed > 0 && r.avg_extra_wait_min != null) {
    tips.push(el("li", {}, "If you miss it, the next ", el("strong", {}, toLabel),
      " comes about ", el("strong", {}, min(r.avg_extra_wait_min)), " later."));
  }
  if (r.to_every_min != null) {
    tips.push(el("li", {}, `The ${toRoute} usually comes every ${min(r.to_every_min)} here.`));
  }
  if (r.safer) {
    tips.push(el("li", { class: "tip" }, el("strong", {}, "Tip: "),
      `plan on a ${toRoute} that leaves at least ${r.safer.buffer_min} min after you arrive, `
      + `and you'd make it ${inTen(r.safer.made_pct)}.`));
  } else if (hasData && r.made_pct < 75) {
    tips.push(el("li", { class: "tip" }, el("strong", {}, "Tip: "), r.advice));
  }
  if (tips.length) body.push(el("ul", { class: "tips" }, ...tips));

  body.push(el("p", { class: "muted small" },
    `We allowed ${r.buffer_min} min to switch buses`
    + (r.accessible_only ? " and counted accessible buses only" : "") + "."));

  if (r.connections > 0) {
    const rows = [
      ["Made the connection", r.made_pct != null ? `${r.made_pct}%` : null],
      ["Times made", `${r.made} of ${r.connections}`],
      ["Planned time between buses", r.avg_planned_gap_min != null ? min(r.avg_planned_gap_min) : null],
      ["Extra wait when missed", r.avg_extra_wait_min != null ? min(r.avg_extra_wait_min) : null],
      ["Cancelled trips not counted", r.cancelled_arrivals ? String(r.cancelled_arrivals) : null],
    ].filter(([, value]) => value != null);
    const details = el("details", { class: "numbers" }, el("summary", {}, "See the numbers"),
      el("dl", {}, ...rows.flatMap(([label, value]) => [el("dt", {}, label), el("dd", {}, value)])));
    if (r.limited_data) {
      details.append(el("p", { class: "muted small" },
        `Based on only ${r.connections} recorded trips, so treat this as a rough guide.`));
    }
    body.push(details);
  }

  result.className = `result ${v.cls}`;
  result.replaceChildren(...body);
  result.hidden = false;
}

function wireTransfers() {
  $("transfer-stop").addEventListener("change", async () => {
    $("transfer-result").hidden = true;
    if (await loadTransferOptions($("transfer-stop").value)) checkTransfer();
  });
  $("transfer-form").addEventListener("submit", checkTransfer);
  // Changing any choice updates the answer right away.
  for (const id of ["transfer-from", "transfer-to", "transfer-buffer", "transfer-day", "transfer-time"]) {
    $(id).addEventListener("change", () => checkTransfer());
  }
  // profile.js updates state.accessibleOnly on the same change event, so check after it runs.
  $("transfer-accessible-only").addEventListener("change", () => setTimeout(checkTransfer));
  // "Check a transfer from here" on the stop screen: open with that stop selected.
  // The tab bar button: open with the last stop viewed, or the first stop.
  document.querySelectorAll('[data-tab="transfers"]').forEach((button) =>
    button.addEventListener("click", () => initTransfers(state.currentStop)));
}

wireTransfers();
