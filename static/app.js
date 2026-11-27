// Will I Make It? rider screens: Map home (UI-2) and Stop detail (UI-3, UI-1).
const REFRESH_MS = 30000; // UI-3: refresh live arrivals within 30 seconds

const state = { stops: [], map: null, markers: {}, currentStop: null, refreshTimer: null,
                accessibleOnly: false };  // UI-5b: one shared accessible setting (see profile.js)

                const $ = (id) => document.getElementById(id);
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null) node.append(c);
  return node;
}

// Show transit times in Waterloo Region time, whatever the device's time zone.
const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], {
  hour: "numeric", minute: "2-digit", timeZone: "America/Toronto" });

// ---------- Navigation ----------
function showScreen(name) {
  for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== `screen-${name}`;
  const tab = name === "stop" ? "map" : name;
  for (const b of document.querySelectorAll(".tabbar button")) {
    if (b.dataset.tab === tab) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
  if (name !== "stop") stopRefresh();
  if (name === "report" && typeof renderReportAccess === "function") {
  renderReportAccess();
}
if (name === "analyst" && typeof loadAnalystReports === "function") {
  loadAnalystReports();
}
  if (name === "map" && state.map) setTimeout(() => state.map.invalidateSize(), 0);
  $("main").focus();
}

document.querySelectorAll("[data-tab]").forEach((b) =>
  b.addEventListener("click", () => showScreen(b.dataset.tab)));
$("back").addEventListener("click", () => {
  showScreen("map");
  history.pushState(null, "", "/");
});
window.addEventListener("popstate", () => routeFromUrl());

// ---------- Status banner ----------
async function loadStatus() {
  try {
    const s = await getJSON("/api/status");
    const banner = $("data-banner");
    if (s.mode === "sample") {
      banner.textContent = "Demo mode: sample stops and simulated delays, not real GRT data.";
      banner.className = "banner";
      banner.hidden = false;
    } else if (!s.live) {
      banner.textContent = "Live GRT data is unavailable right now. Times shown are scheduled.";
      banner.className = "banner warn";
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch (e) { /* the page still works without the banner */ }
}

// ---------- Screen 1: Map home ----------
function initMap(youAreHere) {
  if (typeof L === "undefined") {
    $("map").append(el("p", { class: "map-fallback" },
      "Map could not load. Use the stop list below."));
    return;
  }
  state.map = L.map("map", { keyboard: true }).setView([youAreHere.lat, youAreHere.lon], 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
  }).addTo(state.map);
  L.marker([youAreHere.lat, youAreHere.lon], {
    icon: L.divIcon({ className: "", html: '<div class="you-marker"></div>', iconSize: [16, 16] }),
    title: "You are here", keyboard: false,
  }).addTo(state.map);
}

function letter(i) { return String.fromCharCode(65 + (i % 26)); }

function renderStops() {
  const list = $("stop-list");
  list.replaceChildren();
  Object.values(state.markers).forEach((m) => m.remove());
  state.markers = {};

  if (!state.stops.length) {
    list.append(el("li", { class: "muted" }, "No stops match your search."));
    return;
  }
  state.stops.forEach((s, i) => {
    const access = s.accessible ? "Accessible stop" : "Not wheelchair accessible";
    const routes = s.routes.length ? `Routes ${s.routes.join(", ")}` : "No routes";
    list.append(el("li", {},
      el("button", { class: "stop-card", type: "button", onclick: () => openStop(s.stop_id) },
        el("span", {},
          el("strong", {}, `${letter(i)}  ${s.stop_name}`),
          el("span", { class: "muted small" }, `${routes} · ${access} · ${s.distance_m} m`)),
        el("span", { class: "chevron", "aria-hidden": "true" }, "›"))));

    if (state.map) {
      const marker = L.marker([s.lat, s.lon], {
        title: `${s.stop_name}, ${access}`,
        alt: `${s.stop_name}, ${access}`,
        icon: L.divIcon({
          className: "",
          html: `<div class="stop-marker ${s.accessible ? "" : "not-accessible"}">${letter(i)}</div>`,
          iconSize: [26, 26],
        }),
      }).addTo(state.map);
      marker.on("click", () => openStop(s.stop_id));
      state.markers[s.stop_id] = marker;
    }
  });
  if (state.map) {
    const points = state.stops.slice(0, 6).map((s) => [s.lat, s.lon]);
    state.map.fitBounds(points, { padding: [30, 30], maxZoom: 16 });
  }
}

let searchTimer;
async function loadStops() {
  const params = new URLSearchParams();
  const q = $("search").value.trim();
  if (q) params.set("q", q);
  if (state.accessibleOnly) params.set("accessible", "1");
  const data = await getJSON(`/api/stops?${params}`);
  if (!state.map && !$("map").childElementCount) initMap(data.you_are_here);
  state.stops = data.stops;
  renderStops();
}
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadStops, 200);
});

// ---------- Screen 2: Stop detail ----------
function statusClass(status) {
  const key = String(status || "").toLowerCase()
    .replace(/[\s_-]+/g, "");

  return {
    late: "late",
    ontime: "ontime",
    early: "early",
    cancelled: "cancelled",
    scheduled: "scheduled"
  }[key] || "scheduled";
}

function renderAlerts(alerts) {
  const box = $("stop-alerts");
  box.replaceChildren(...alerts.map((a) =>
    el("div", { class: "alert", role: "note" },
      el("strong", {}, `${a.effect_label || "Service alert"}: ${a.header}`),
      a.description ? el("span", { class: "small" }, a.description) : null)));
}
function updateFeedAge() {
  if (state.feedAge == null) {
    $("updated-at").textContent = "Not updated yet";
    return;
  }

  const elapsed = Math.floor(
    (Date.now() - state.feedReceivedAt) / 1000
  );

  $("updated-at").textContent =
    `Updated ${state.feedAge + elapsed} s ago`;
}
// Icons sit next to the status words, so the status never relies on colour alone.
const STATUS_ICON = { late: "▲", ontime: "✓", early: "◀", cancelled: "✕", scheduled: "◷" };

function statusPill(a) {
  const cls = statusClass(a.status);
  return el("span", { class: `status pill ${cls}` },
    el("span", { "aria-hidden": "true" }, `${STATUS_ICON[cls]} `), a.status_label);
}

// One card per route and direction: the next bus is shown big, later ones on a "Then" line.
function groupArrivals(arrivals) {
  const groups = new Map();
  for (const a of arrivals) {
    const key = `${a.route}|${a.headsign}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(a);
  }
  return [...groups.values()];
}

const minutesText = (a) => (a.minutes_away === 0 ? "Due now" : `${a.minutes_away} min`);

function arrivalCard(group) {
  const [a, ...later] = group;
  const cancelled = statusClass(a.status) === "cancelled";

  let mins;
  if (cancelled) mins = el("div", { class: "arrival-mins none", "aria-hidden": "true" }, "–");
  else if (a.minutes_away === 0) mins = el("div", { class: "arrival-mins" }, "Now");
  else mins = el("div", { class: "arrival-mins" }, String(a.minutes_away), el("span", {}, "min"));

  const when = cancelled
    ? el("span", { class: "muted small arrival-when" }, "Not running. Was ",
        el("span", { class: "cancelled-time" }, fmtTime(a.scheduled)))
    : el("span", { class: "muted small arrival-when" },
        ...(a.live
          ? [el("span", {}, `Arrives ${fmtTime(a.expected)}`), el("span", {}, ` · scheduled ${fmtTime(a.scheduled)}`)]
          : [el("span", {}, `Scheduled ${fmtTime(a.scheduled)}`)]));

  const card = el("li", { class: "arrival-card" },
    el("div", { class: "arrival-head" },
      el("span", { class: "route-badge" }, a.route),
      el("strong", { class: "arrival-dir" }, el("span", { class: "muted small" }, "to "), a.headsign)),
    el("div", { class: "arrival-main" },
      mins,
      el("div", { class: "right" },
        statusPill(a),
        when,
        el("span", { class: "arrival-tags" },
          a.detour ? el("span", { class: "tag detour-tag" }, "Detour") : null,
          a.accessibility
            ? el("span", { class: a.accessible ? "trip-access" : "trip-access no" }, a.accessibility)
            : null))));

  if (later.length) {
    card.append(el("div", { class: "arrival-then" },
      el("span", { class: "muted small" }, "Then"),
      el("span", { class: "then-list" }, ...later.slice(0, 2).map((n) => {
        const gone = statusClass(n.status) === "cancelled";
        return el("span", { class: "then-item" },
          el("strong", {}, gone ? fmtTime(n.scheduled) : minutesText(n)),
          ` · ${n.status_label}`,
          n.accessibility && !n.accessible
            ? el("span", { class: "trip-access no" }, ` · ${n.accessibility}`) : null);
      }))));
  }
  return card;
}

async function loadArrivals() {
  const stopId = state.currentStop;
  if (!stopId) return;
  try {
    const access = state.accessibleOnly ? "?accessible=1" : "";
    const data = await getJSON(`/api/stops/${encodeURIComponent(stopId)}/arrivals${access}`);    if (state.currentStop !== stopId) return;
    renderAlerts(data.alerts);
    const tag = $("live-tag");
    tag.textContent = data.live ? "Live" : "Scheduled only";
    tag.className = `tag ${data.live ? "live" : "scheduled"}`;
    state.feedAge = data.feed_age_seconds;
state.feedReceivedAt = Date.now();
updateFeedAge();
   $("arrivals-notice").hidden = !data.stale && !data.notice;

$("arrivals-notice").textContent = data.stale
  ? "Live data is delayed. Times may be out of date."
  : data.notice || "";
    $("accessibility-notice").hidden = !data.accessibility_notice;
    $("accessibility-notice").textContent = data.accessibility_notice || "";

    const list = $("arrivals");
    if (!data.arrivals.length) {
      list.replaceChildren(el("li", { class: "muted" }, "No buses or trains in the next 90 minutes."));
      return;
    }
    list.replaceChildren(...groupArrivals(data.arrivals).map(arrivalCard));
  } catch (e) {
    $("arrivals-notice").hidden = false;
    $("arrivals-notice").textContent = "Could not load arrivals. Retrying in 30 seconds.";
  }
}

async function loadReliability() {
  const stopId = state.currentStop;
  const day = $("filter-day").value;
  const time = $("filter-time").value;
  const data = await getJSON(
    `/api/stops/${encodeURIComponent(stopId)}/reliability?day=${day}&time=${time}`
    + (state.accessibleOnly ? "&accessible=1" : ""));
  const dayLabel = day === "all" ? "All days" : $("filter-day").selectedOptions[0].textContent;
  const timeLabel = time === "all" ? "all times" : $("filter-time").selectedOptions[0].textContent;
  $("reliability-caption").textContent =
  `${dayLabel}, ${timeLabel.toLowerCase()}${state.accessibleOnly ? ", accessible buses only" : ""}, `
  + "from recorded arrivals. These are estimates, not guarantees.";

  const list = $("reliability");
  if (!data.routes.length) {
    list.replaceChildren(el("li", { class: "muted" }, "No recorded arrivals for these filters yet."));
    return;
  }
  list.replaceChildren(...data.routes.map((r) => {
    if (r.trips === 0) {
      return el("li", { class: "muted" }, `${r.short_name}: no recorded arrivals (${r.cancelled} cancelled).`);
    }
    const [headline, band] = reliabilityWords(r.on_time_pct);
    const avg = r.avg_delay_min;
    const avgFull = avg >= 0 ? `${avg} min late` : `${Math.abs(avg)} min early`;
    return el("li", { class: `rel-item ${band}` },
      el("div", { class: "rel-row" },
        el("span", { class: "route-badge small-badge" }, r.short_name),
        el("div", { class: "rel-text" },
          el("strong", {}, headline),
          el("span", { class: "muted small" }, `${tripsInTen(r.on_time_pct)} · ${usualDelay(avg)}`))),
      el("div", { class: "bar", role: "img", "aria-label": `${r.on_time_pct} percent on time` },
        el("span", { style: `width:${r.on_time_pct}%` })),
      r.limited_data ? el("span", { class: "muted small" }, "Limited data: treat this as a rough estimate.") : null,
      el("details", { class: "numbers" }, el("summary", {}, "See the numbers"),
        el("dl", {},
          el("dt", {}, "On time"), el("dd", {}, `${r.on_time} of ${r.trips} trips (${r.on_time_pct}%)`),
          el("dt", {}, "Average delay"), el("dd", {}, avgFull),
          ...(r.cancelled ? [el("dt", {}, "Cancelled trips not counted"), el("dd", {}, String(r.cancelled))] : []))));
  }));
}

// Wording only: the same on-time % and average delay, said the way a rider would.
function reliabilityWords(pct) {
  if (pct >= 90) return ["Usually on time", "good"];
  if (pct >= 75) return ["Mostly on time", "good"];
  if (pct >= 50) return ["Hit or miss", "fair"];
  return ["Rarely on time", "poor"];
}
function tripsInTen(pct) {
  const n = Math.round(pct / 10);
  if (n >= 10) return "Almost every trip on time";
  if (n <= 0) return "Almost no trips on time";
  return `About ${n} in 10 trips on time`;
}
function usualDelay(avg) {
  const m = Math.round(Math.abs(avg));
  if (m === 0) return "usually right on schedule";
  return `usually about ${m} min ${avg > 0 ? "late" : "early"}`;
}
$("filter-day").addEventListener("change", loadReliability);
$("filter-time").addEventListener("change", loadReliability);

function stopRefresh() {
  clearInterval(state.refreshTimer);
  clearInterval(state.ageTimer);
  state.refreshTimer = null;
  state.ageTimer = null;
}

async function openStop(stopId, push = true) {
  state.currentStop = stopId;
  if (push) history.pushState({ stopId }, "", `/?stop=${encodeURIComponent(stopId)}`);
  const s = await getJSON(`/api/stops/${encodeURIComponent(stopId)}`);
  $("stop-title").textContent = s.stop_name;
  $("stop-badges").replaceChildren(
    el("span", { class: s.accessible ? "badge" : "badge warn" },
      s.accessible ? "Accessible stop" : "Not wheelchair accessible"),
    el("span", { class: "badge" }, `Stop #${s.stop_code || s.stop_id}`));
  renderAlerts(s.alerts);
  $("arrivals").replaceChildren(el("li", { class: "muted" }, "Loading arrivals..."));
  showScreen("stop");
  $("show-resolved").checked = false;
$("barrier-heading").textContent = `Barrier reports (${s.open_reports || 0})`;

if (typeof loadStopReports === "function") {
  loadStopReports();
}
  stopRefresh();
  await Promise.all([loadArrivals(), loadReliability()]);
  if (state.currentStop !== stopId || $("screen-stop").hidden) return;
  state.refreshTimer = setInterval(() => { loadArrivals(); loadStatus(); }, REFRESH_MS);
  state.ageTimer = setInterval(updateFeedAge, 1000);
}

async function loadFilters() {
  const f = await getJSON("/api/filters");
  const fill = (select, items) => select.replaceChildren(
    el("option", { value: "all" }, "All"),
    ...items.map((i) => el("option", { value: i.key }, i.label)));
  fill($("filter-day"), f.days);
  fill($("filter-time"), f.times);
}

function routeFromUrl() {
  const stop = new URLSearchParams(location.search).get("stop");
  if (stop) openStop(stop, false);
  else showScreen("map");
}

(async function init() {
  await Promise.all([loadStatus(), loadFilters(), loadStops()]);
  routeFromUrl();
})();
