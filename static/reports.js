// UI-6b: barrier reporting and admin management

let reportStops = [];
let reportStopId = null;
let stopReportRequest = 0;
let adminReportRequest = 0;
let reportSubmitting = false;

function reportMessage(message) {
  const box = $("report-message");
  box.textContent = message;
  box.hidden = !message;

  if (message && !$("screen-report").hidden) {
    box.focus();
  }
}

function renderReportAccess() {
  $("report-login-required").hidden = Boolean(state.user);
  $("report-form").hidden = !state.user;

  const isAdmin = state.user?.role === "admin";
  $("admin-section").hidden = !isAdmin;

  if (!isAdmin) {
    adminReportRequest++;
    $("admin-reports").replaceChildren();
    $("admin-message").hidden = true;
  }

  if (!$("screen-report").hidden) {
    if (state.user) loadReportStops();
    if (isAdmin) loadAdminReports();
  }
}

async function loadReportStops() {
  try {
    const data = await apiRequest("/api/stops");
    reportStops = data.stops;

    if (reportStopId) {
      $("report-search").value = "";
    }

    renderReportStops(reportStopId);
  } catch (error) {
    reportMessage("Could not load stops. Please try again.");
  }
}

function renderReportStops(selected = null) {
  const query = $("report-search").value.trim().toLowerCase();

  const matches = reportStops.filter((stop) =>
    stop.stop_name.toLowerCase().includes(query) ||
    String(stop.stop_code || "").includes(query)
  );

  $("report-stop").replaceChildren(
    el("option", { value: "" }, "Choose a stop"),
    ...matches.map((stop) =>
      el("option", { value: stop.stop_id }, stop.stop_name)
    )
  );

  if (selected) {
    $("report-stop").value = selected;
  }
}

async function submitBarrierReport(event) {
  event.preventDefault();
  if (reportSubmitting) return;

  const stopId = $("report-stop").value;
  const category = $("report-category").value;
  const description = $("report-description").value.trim();
  const button = $("report-form").querySelector('[type="submit"]');

  if (!stopId || !category || !description) {
    reportMessage("Choose a stop and barrier type, and enter a description.");
    return;
  }

  reportSubmitting = true;
  button.disabled = true;
  reportMessage("");

  try {
    await apiRequest(
      `/api/stops/${encodeURIComponent(stopId)}/reports`,
      "POST",
      { category, description }
    );

    $("report-form").reset();
    reportStopId = null;
    renderReportStops();
    $("report-counter").textContent = "0 / 500";

    reportMessage("Thanks! Your report is Open.");

    if (state.user?.role === "admin") {
      loadAdminReports();
    }

  } catch (error) {
    if (error.status === 401) {
      state.user = null;
      renderAuth();
      reportMessage("Your session ended. Please log in again.");

    } else if (error.status === 429) {
      reportMessage(
        `You've sent several reports recently. Try again in ${error.data.retry_after_minutes} minutes.`
      );

    } else {
      reportMessage(error.message);
    }
  } finally {
    reportSubmitting = false;
    button.disabled = false;
  }
}

function reportCard(report, admin = false) {
  const card = el("li", { class: "report-card" },
    el("strong", {}, report.category_label),

    el("span", {
      class: `report-status ${report.status}`
    }, report.status_label),

    admin
      ? el("p", { class: "small" }, report.stop_name)
      : null,

    el("p", {}, report.description),

    el("p", { class: "muted small" },
      new Date(report.created_at).toLocaleDateString("en-CA")
    )
  );

  if (admin) {
    card.append(
      el("p", { class: "muted small" },
        `Reported by: ${report.reported_by}`
      )
    );

    if (report.status === "open") {
      card.append(
        el("button", {
          class: "secondary",
          type: "button",
          onclick: () => changeReportStatus(report.id, "under_review")
        }, "Start review")
      );
    }

    if (report.status === "under_review") {
      card.append(
        el("button", {
          class: "primary",
          type: "button",
          onclick: () => changeReportStatus(report.id, "resolved")
        }, "Mark resolved"),

        el("button", {
          class: "secondary",
          type: "button",
          onclick: () => changeReportStatus(report.id, "open")
        }, "Send back to open")
      );
    }
  }

  return card;
}

async function loadStopReports() {
  const stopId = state.currentStop;
  if (!stopId) return;

  const requestId = ++stopReportRequest;
  const list = $("stop-reports");
  const resolved = $("show-resolved").checked;

  list.replaceChildren(el("li", { class: "muted" }, "Loading reports..."));

  try {
    const data = await apiRequest(
      `/api/stops/${encodeURIComponent(stopId)}/reports?include_resolved=${resolved ? 1 : 0}`
    );

    if (requestId !== stopReportRequest ||
        state.currentStop !== stopId ||
        $("screen-stop").hidden) return;

    const reports = data.reports;
    const active = reports.filter((r) => r.status !== "resolved");

    $("barrier-heading").textContent =
      `Barrier reports (${active.length})`;

    list.replaceChildren(
      ...reports.map((report) => reportCard(report))
    );

    if (!reports.length) {
      list.append(
        el("li", { class: "muted" }, "No barrier reports at this stop.")
      );
    }

  } catch (error) {
    if (requestId !== stopReportRequest ||
        state.currentStop !== stopId) return;

    list.replaceChildren(
      el("li", {}, "Could not load barrier reports.")
    );
  }
}

function adminMessage(message) {
  $("admin-message").textContent = message;
  $("admin-message").hidden = !message;
}

async function loadAdminReports() {
  if (state.user?.role !== "admin") return;

  const requestId = ++adminReportRequest;
  const list = $("admin-reports");
  const status = $("admin-filter").value;

  list.replaceChildren(
    el("li", { class: "muted" }, "Loading reports...")
  );

  try {
    const data = await apiRequest(
      `/api/reports?status=${encodeURIComponent(status)}`
    );

    if (requestId !== adminReportRequest ||
        state.user?.role !== "admin") return;

    list.replaceChildren(
      ...data.reports.map((report) => reportCard(report, true))
    );

    if (!data.reports.length) {
      list.append(
        el("li", { class: "muted" }, "No reports match this filter.")
      );
    }

  } catch (error) {
    if (requestId !== adminReportRequest) return;

    list.replaceChildren();

    adminMessage(
      error.status === 401 || error.status === 403
        ? "Admin access only. Please check your login."
        : error.message
    );
  }
}

async function changeReportStatus(id, status) {
  if (state.user?.role !== "admin") return;

  adminMessage("");

  try {
    const data = await apiRequest(
      `/api/reports/${id}`,
      "PATCH",
      { status }
    );

    adminMessage(`Report updated to ${data.status_label}.`);
    await loadAdminReports();

  } catch (error) {
    adminMessage(error.message);
  }
}

function initReports() {
  $("report-form").addEventListener("submit", submitBarrierReport);

  $("report-description").addEventListener("input", () => {
    $("report-counter").textContent =
      `${$("report-description").value.length} / 500`;
  });

  $("report-search").addEventListener("input", () => {
    renderReportStops();
  });

  $("report-stop").addEventListener("change", () => {
    reportStopId = $("report-stop").value;
  });

  $("show-resolved").addEventListener("change", loadStopReports);

  $("admin-filter").addEventListener("change", () => {
    adminMessage("");
    loadAdminReports();
  });

  $("report-this-stop").addEventListener("click", () => {
    reportStopId = state.currentStop;
    $("report-search").value = "";
    renderReportAccess();
  });

  document.addEventListener("auth-changed", renderReportAccess);

  renderReportAccess();
}

initReports();