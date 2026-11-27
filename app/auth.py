"""UI-6a: user accounts, logins and role checks.

Passwords are hashed with werkzeug.security and never stored, logged or returned.
The logged-in user's id lives in Flask's signed session cookie.
"""
import re
from functools import wraps

from flask import current_app, g, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash

from . import db, timeutil

ROLES = ("rider", "analyst", "admin")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LENGTH = 8

# Class demo only. Created by `python run.py --reset`.
DEMO_PASSWORD = "demo-password"
DEMO_USERS = (("rider_demo", "rider"), ("analyst_demo", "analyst"), ("admin_demo", "admin"))

LOGIN_ERROR = "Wrong username or password"


class UsernameTaken(Exception):
    pass


def validate_credentials(username, password):
    """Return an error message for bad register input, or None when it is fine."""
    if not isinstance(username, str) or not USERNAME_RE.match(username):
        return "Username must be 3 to 30 letters, numbers or _."
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def public_user(row):
    """The user fields the API may return. Never the password hash."""
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def get_user(conn, user_id):
    row = conn.execute("SELECT id, username, role FROM users WHERE id = ?", (user_id,)).fetchone()
    return public_user(row)


def create_user(conn, username, password, role="rider", now=None):
    """Insert a user with a hashed password and return the public user dict."""
    if role not in ROLES:
        raise ValueError(f"Unknown role: {role}")
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        raise UsernameTaken(username)
    created_at = (now or timeutil.now_local()).isoformat()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), role, created_at))
    conn.commit()
    return get_user(conn, cur.lastrowid)


def check_login(conn, username, password):
    """Return the user dict when the username and password match, otherwise None."""
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    row = conn.execute(
        "SELECT id, username, role, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return public_user(row)


def seed_demo_users(conn, now=None):
    """Create the three demo accounts if they don't exist. Returns how many were added."""
    added = 0
    for username, role in DEMO_USERS:
        try:
            create_user(conn, username, DEMO_PASSWORD, role, now)
            added += 1
        except UsernameTaken:
            pass
    return added


def _request_conn():
    """The request's database connection, shared with the routes in api.py."""
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DB_PATH"])
    return g.conn


def login_user(user):
    # Clear first so an old session can't carry over into the new login.
    session.clear()
    session["user_id"] = user["id"]


def logout_user():
    session.clear()


def current_user(conn=None):
    """The logged-in user's dict, or None. Reads session["user_id"]."""
    user_id = session.get("user_id")
    if user_id is None:
        return None
    return get_user(conn or _request_conn(), user_id)


def login_required(view):
    """401 when nobody is logged in. Sets g.user for the view."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        g.user = current_user()
        if g.user is None:
            return jsonify({"error": "Please log in first."}), 401
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """401 when logged out, 403 when the user's role isn't one of `roles`. Sets g.user."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            g.user = current_user()
            if g.user is None:
                return jsonify({"error": "Please log in first."}), 401
            if g.user["role"] not in roles:
                return jsonify({"error": "You don't have access to this."}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator
