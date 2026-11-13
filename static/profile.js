// Loaded after app.js, so it can use app.js helpers: $, state, loadStops,
// loadArrivals, loadReliability.
//
// The rule: ONE shared setting, state.accessibleOnly. Every checkbox marked
// data-accessible-toggle (map, stop screen, transfer screen) shows and changes it.
// The backend filter is ?accessible=1 (see docs/sprint2.md, UI-5a).

const PROFILE_KEY = "wimi.profile";  // localStorage key; value is JSON {accessibleOnly: true|false}

// Turn the shared filter on or off, keep every toggle in sync, and reload what's on screen.
function setAccessibleOnly(on) {
  state.accessibleOnly = Boolean(on);
  document.querySelectorAll("[data-accessible-toggle]").forEach((box) => {
    box.checked = state.accessibleOnly;
  });
  loadStops();
  if (state.currentStop && !$("screen-stop").hidden) {
    loadArrivals();
    loadReliability();
  }
  // Re-run the transfer check if a result is showing (UI-4b).
  if (typeof checkTransfer === "function" && $("transfer-result") && !$("transfer-result").hidden) {
    $("transfer-form").requestSubmit();
  }
}

// Read the saved profile. localStorage can be blocked, so never let it break the page.
function loadProfile() {
  try {
    const saved = JSON.parse(localStorage.getItem(PROFILE_KEY));
    return saved && typeof saved === "object" ? { accessibleOnly: Boolean(saved.accessibleOnly) } : null;
  } catch (e) {
    return null;
  }
}

function showProfileStatus(message) {
  $("profile-status").textContent = message;
  $("profile-status").hidden = false;
}

function saveProfile(event) {
  event.preventDefault();
  const accessibleOnly = $("profile-accessible").checked;
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify({ accessibleOnly }));
    showProfileStatus("Profile saved on this device.");
  } catch (e) {
    showProfileStatus("Could not save on this device, but the setting is on for this visit.");
  }
  $("profile-note").hidden = !accessibleOnly;
  setAccessibleOnly(accessibleOnly);
}

function clearProfile() {
  try { localStorage.removeItem(PROFILE_KEY); } catch (e) { /* nothing saved to clear */ }
  $("profile-accessible").checked = false;
  $("profile-note").hidden = true;
  setAccessibleOnly(false);
  showProfileStatus("Profile cleared.");
}

function initProfile() {
  document.querySelectorAll("[data-accessible-toggle]").forEach((box) =>
    box.addEventListener("change", () => setAccessibleOnly(box.checked)));
  $("profile-form").addEventListener("submit", saveProfile);
  $("profile-clear").addEventListener("click", clearProfile);

  const profile = loadProfile();
  if (profile && profile.accessibleOnly) {
    $("profile-accessible").checked = true;
    $("profile-note").hidden = false;
    setAccessibleOnly(true);
  }
}

initProfile();