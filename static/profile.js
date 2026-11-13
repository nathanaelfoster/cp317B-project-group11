// UI-5b: Accessibility filter (shared toggle) and optional accessibility profile.
//
// Loaded after app.js (add <script src="/static/profile.js"></script> below app.js in
// index.html), so it can use app.js helpers: $, el, getJSON, state, loadStops,
// loadArrivals, loadReliability.
//
// The rule: ONE shared setting, state.accessibleOnly. Every checkbox marked
// data-accessible-toggle (map, stop screen, transfer screen) shows and changes it.
// The backend filter is ?accessible=1 (see docs/sprint2.md, UI-5a).

const PROFILE_KEY = "wimi.profile";  // localStorage key; value is JSON {accessibleOnly: true|false}

// Turn the shared filter on or off.
// - set state.accessibleOnly
// - tick/untick every [data-accessible-toggle] checkbox to match
// - reload the stop list, and arrivals + reliability if a stop is open
//   (and re-run the transfer check if a result is showing)
function setAccessibleOnly(on) {
  // TODO(UI-5b)
}

// Read the saved profile. Wrap localStorage in try/catch: it can be blocked
// (private windows, strict browser settings) and the app must still work.
// Returns {accessibleOnly: bool}, or null when nothing is saved.
function loadProfile() {
  // TODO(UI-5b)
  return null;
}

// Submit handler for #profile-form.
// Save {accessibleOnly: <#profile-accessible checked>} to localStorage, call
// setAccessibleOnly() to match, and show "Profile saved on this device." in #profile-status.
function saveProfile(event) {
  event.preventDefault();
  // TODO(UI-5b)
}

// Click handler for #profile-clear.
// Remove the saved profile, setAccessibleOnly(false), untick #profile-accessible,
// and show "Profile cleared." in #profile-status.
function clearProfile() {
  // TODO(UI-5b)
}

// Run once on page load:
// - wire every [data-accessible-toggle] checkbox: on change -> setAccessibleOnly(checkbox.checked)
// - wire #profile-form (submit -> saveProfile) and #profile-clear (click -> clearProfile)
// - if loadProfile() says accessibleOnly, tick #profile-accessible, show #profile-note
//   ("Turned on by your accessibility profile.") and call setAccessibleOnly(true)
function initProfile() {
  // TODO(UI-5b)
}

initProfile();
