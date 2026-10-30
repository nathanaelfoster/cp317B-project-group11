// Will I Make It? rider screens: Map home (UI-2) and Stop detail (UI-3, UI-1).
const REFRESH_MS = 30000; // UI-3: refresh live arrivals within 30 seconds

const state = { stops: [], map: null, markers: {}, currentStop: null, refreshTimer: null };
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
  if ($("accessible-only").checked) params.set("accessible", "1");
  const data = await getJSON(`/api/stops?${params}`);
  if (!state.map && !$("map").childElementCount) initMap(data.you_are_here);
  state.stops = data.stops;
  renderStops();
}
$("search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadStops, 200);
});
$("accessible-only").addEventListener("change", loadStops);

// ---------- Screen 2: Stop detail ----------
function statusClass(status) {
  return { "Late": "late", "On time": "ontime", "Early": "early",
           "Cancelled": "cancelled", "Scheduled": "scheduled" }[status] || "scheduled";
}

function renderAlerts(alerts) {
  const box = $("stop-alerts");
  box.replaceChildren(...alerts.map((a) =>
    el("div", { class: "alert", role: "note" },
      el("strong", {}, `Service alert: ${a.header}`),
      a.description ? el("span", { class: "small" }, a.description) : null)));
}

async function loadArrivals() {
  const stopId = state.currentStop;
  if (!stopId) return;
  try {
    const data = await getJSON(`/api/stops/${encodeURIComponent(stopId)}/arrivals`);
    if (state.currentStop !== stopId) return;
    renderAlerts(data.alerts);
    const tag = $("live-tag");
    tag.textContent = data.live ? "Live" : "Scheduled only";
    tag.className = `tag ${data.live ? "live" : "scheduled"}`;
    $("updated-at").textContent = `Updated ${fmtTime(data.updated_at)}`;
    $("arrivals-notice").hidden = !data.notice;
    $("arrivals-notice").textContent = data.notice || "";

    const list = $("arrivals");
    if (!data.arrivals.length) {
      list.replaceChildren(el("li", { class: "muted" }, "No buses or trains in the next 90 minutes."));
      return;
    }
    list.replaceChildren(...data.arrivals.map((a) => {
      const when = a.status === "Cancelled"
        ? "Not running"
        : `${a.is_live ? "Arrives" : "Scheduled"} ${fmtTime(a.expected)}`
          + (a.minutes_away === 0 ? " (due now)" : ` (${a.minutes_away} min)`);
      return el("li", {},
        el("span", {},
          el("strong", {}, `${a.route} to ${a.headsign}`),
          el("span", { class: "muted small", style: "display:block" }, `Scheduled ${fmtTime(a.scheduled)}`)),
        el("span", { class: "right" },
          el("span", { class: `status ${statusClass(a.status)}` }, a.label),
          el("span", { class: "muted small", style: "display:block" }, when)));
    }));
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
    `/api/stops/${encodeURIComponent(stopId)}/reliability?day=${day}&time=${time}`);
  const dayLabel = day === "all" ? "All days" : $("filter-day").selectedOptions[0].textContent;
  const timeLabel = time === "all" ? "all times" : $("filter-time").selectedOptions[0].textContent;
  $("reliability-caption").textContent =
    `${dayLabel}, ${timeLabel.toLowerCase()}, from recorded arrivals. These are estimates, not guarantees.`;

  const list = $("reliability");
  if (!data.routes.length) {
    list.replaceChildren(el("li", { class: "muted" }, "No recorded arrivals for these filters yet."));
    return;
  }
  list.replaceChildren(...data.routes.map((r) => {
    if (r.trips === 0) {
      return el("li", { class: "muted" }, `${r.short_name}: no recorded arrivals (${r.cancelled} cancelled).`);
    }
    const avg = r.avg_delay_min;
    const avgText = avg >= 0 ? `avg ${avg} min late` : `avg ${Math.abs(avg)} min early`;
    return el("li", {},
      el("div", { class: "rel-row" },
        el("strong", {}, `${r.short_name} on time ${r.on_time} of ${r.trips} trips (${r.on_time_pct}%)`),
        el("span", {}, avgText)),
      el("div", { class: "bar", role: "img", "aria-label": `${r.on_time_pct} percent on time` },
        el("span", { style: `width:${r.on_time_pct}%` })),
      r.limited_data ? el("span", { class: "muted small" }, "Limited data: treat this as a rough estimate.") : null,
      r.cancelled ? el("span", { class: "muted small", style: "display:block" }, `${r.cancelled} cancelled trips not counted.`) : null);
  }));
}
$("filter-day").addEventListener("change", loadReliability);
$("filter-time").addEventListener("change", loadReliability);

function stopRefresh() {
  clearInterval(state.refreshTimer);
  state.refreshTimer = null;
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
  stopRefresh();
  await Promise.all([loadArrivals(), loadReliability()]);
  state.refreshTimer = setInterval(() => { loadArrivals(); loadStatus(); }, REFRESH_MS);
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
