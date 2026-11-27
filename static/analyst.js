
// REP-4b: Analyst dashboard

let analystRequest = 0;
let analystFiltersReady = false;

function hasAnalystAccess() {
  return ["analyst", "admin"].includes(state.user?.role);
}

function renderAnalystAccess() {
  const allowed = hasAnalystAccess();

  $("analyst-tab").hidden = !allowed;

  if (!allowed) {
    analystRequest++;

    ["analyst-routes", "analyst-hotspots",
     "analyst-summary", "analyst-categories"].forEach((id) => {
      $(id).replaceChildren();
    });

    if (!$("screen-analyst").hidden) {
      showScreen("profile");
    }
  } else if (!$("screen-analyst").hidden) {
    loadAnalystReports();
  }
}

function analystMessage(message) {
  $("analyst-message").textContent = message;
  $("analyst-message").hidden = !message;
}

function analystTable(caption, headings, rows) {
  return el("table", { class: "analyst-table" },

    el("caption", {}, caption),

    el("thead", {},
      el("tr", {},
        ...headings.map((heading) =>
          el("th", { scope: "col" }, heading)
        )
      )
    ),

    el("tbody", {},
      ...rows.map((row) =>
        el("tr", {},
          ...row.map((value) =>
            el("td", {}, value ?? "—")
          )
        )
      )
    )
  );
}

async function loadAnalystFilters() {
  if (analystFiltersReady) return;

  const filters = await apiRequest("/api/filters");

  function fill(id, items) {
    $(id).replaceChildren(
      el("option", { value: "all" }, "All"),
      ...items.map((item) =>
        el("option", { value: item.key }, item.label)
      )
    );
  }

  fill("analyst-day", filters.days);
  fill("analyst-time", filters.times);

  analystFiltersReady = true;
}

function renderAnalystRoutes(data) {
  const container = $("analyst-routes");

  if (!data.routes.length) {
    container.replaceChildren(
      el("p", { class: "muted small" },
        "No routes have enough recorded trips for these filters.")
    );
    return;
  }

  const rows = data.routes.map((route) => [
    route.route,
    route.trips,
    route.on_time_pct == null
      ? "—"
      : `${route.on_time_pct}%`,
    route.avg_delay_min == null
      ? "—"
      : `${route.avg_delay_min} min`,
    route.cancelled
  ]);

  container.replaceChildren(
    analystTable(
      "Accessible route reliability",
      ["Route", "Trips", "On time", "Avg. delay", "Cancelled"],
      rows
    )
  );
}

function renderAnalystHotspots(data) {
  const container = $("analyst-hotspots");

  if (!data.stops.length) {
    container.replaceChildren(
      el("p", { class: "muted" },
        "No barrier reports in this period.")
    );
    return;
  }

  const rows = data.stops.map((stop) => [
    el("button", {
      class: "analyst-stop-link",
      type: "button",
      onclick: () => openStop(stop.stop_id)
    }, stop.stop_name),

    stop.total,
    stop.open,
    stop.under_review,
    stop.resolved,
    stop.top_category_label
  ]);

  container.replaceChildren(
    analystTable(
      "Stops with the most barrier reports",
      ["Stop", "Total", "Open", "Review", "Resolved", "Top barrier"],
      rows
    )
  );
}

function renderAnalystResolution(data) {
  function metric(label, value) {
    return el("div", { class: "analyst-metric" },
      el("strong", {}, String(value)),
      el("span", { class: "muted small" }, label)
    );
  }

  $("analyst-summary").replaceChildren(
    metric("Average hours", data.avg_hours ?? "—"),
    metric("Median hours", data.median_hours ?? "—"),
    metric("Unresolved", data.unresolved)
  );

  const container = $("analyst-categories");

  if (!data.by_category.length) {
    container.replaceChildren(
      el("p", { class: "muted" },
        "No reports resolved in this period.")
    );
    return;
  }

  const rows = data.by_category.map((category) => [
    category.label,
    category.resolved,
    category.avg_hours ?? "—",
    category.median_hours ?? "—"
  ]);

  container.replaceChildren(
    analystTable(
      "Resolution time by barrier type",
      ["Category", "Resolved", "Avg. hours", "Median hours"],
      rows
    )
  );
}

async function loadAnalystReports() {
  if (!hasAnalystAccess()) {
    analystMessage("Analyst access only.");
    return;
  }

  const requestId = ++analystRequest;

  analystMessage("Loading...");

  try {
    await loadAnalystFilters();

    const params = new URLSearchParams({
      days: $("analyst-days").value,
      day: $("analyst-day").value,
      time: $("analyst-time").value
    });

    const [routes, hotspots, resolution] = await Promise.all([
      apiRequest(`/api/analyst/accessible-routes?${params}`),
      apiRequest("/api/analyst/report-hotspots?days=90"),
      apiRequest("/api/analyst/resolution-time?days=90")
    ]);

    if (requestId !== analystRequest ||
        !hasAnalystAccess() ||
        $("screen-analyst").hidden) return;

    renderAnalystRoutes(routes);
    renderAnalystHotspots(hotspots);
    renderAnalystResolution(resolution);

    analystMessage("");

  } catch (error) {
    if (requestId !== analystRequest) return;

    ["analyst-routes", "analyst-hotspots",
     "analyst-summary", "analyst-categories"].forEach((id) => {
      $(id).replaceChildren();
    });

    analystMessage(
      error.status === 401 || error.status === 403
        ? "Analyst access only."
        : "Could not load analyst reports. Please try again."
    );
  }
}

function initAnalyst() {
  ["analyst-days", "analyst-day", "analyst-time"].forEach((id) => {
    $(id).addEventListener("change", loadAnalystReports);
  });

  document.addEventListener("auth-changed", renderAnalystAccess);

  renderAnalystAccess();
}

initAnalyst();
