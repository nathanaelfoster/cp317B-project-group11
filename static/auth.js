// UI-6b: authentication and shared user session

state.user = null;

async function apiRequest(url, method = "GET", body = null) {
  const options = {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" }
  };

  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);
  const data = await response.json();

  if (!response.ok) {
    const error = new Error(data.error || "Request failed.");
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
}

function showAuthMessage(message) {
  const box = $("auth-message");
  box.textContent = message;
  box.hidden = !message;
}

function renderAuth() {
  const user = state.user;

  $("auth-form").hidden = Boolean(user);
  $("auth-account").hidden = !user;

  $("auth-user").textContent = user
    ? `Logged in as ${user.username} (${user.role})`
    : "";

  document.dispatchEvent(new Event("auth-changed"));
}

async function loadCurrentUser() {
  try {
    const data = await apiRequest("/api/auth/me");
    state.user = data.user;
    renderAuth();
  } catch (error) {
    showAuthMessage("Could not check your login status.");
  }
}

async function authenticate(action) {
  const username = $("auth-username").value.trim();
  const password = $("auth-password").value;

  showAuthMessage("");

  if (!username || !password) {
    showAuthMessage("Enter your username and password.");
    return;
  }

  try {
    const data = await apiRequest(
      `/api/auth/${action}`,
      "POST",
      { username, password }
    );

    state.user = data.user;
    $("auth-form").reset();
    renderAuth();

    showAuthMessage(
      action === "register"
        ? "Account created. You are now logged in."
        : "Logged in successfully."
    );
  } catch (error) {
    showAuthMessage(error.message);
  }
}

async function logout() {
  try {
    await apiRequest("/api/auth/logout", "POST");
    state.user = null;
    renderAuth();
    showAuthMessage("Logged out successfully.");
  } catch (error) {
    showAuthMessage(error.message);
  }
}

function initAuth() {
  $("auth-form").addEventListener("submit", (event) => {
    event.preventDefault();
    authenticate("login");
  });

  $("auth-register").addEventListener("click", () => {
    authenticate("register");
  });

  $("auth-logout").addEventListener("click", logout);

  loadCurrentUser();
}

initAuth();
