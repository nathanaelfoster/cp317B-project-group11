"""UI-6a Part 1: accounts, logins, logout, /me and role checks."""
import pytest
from flask import jsonify

from app import auth
from app.api import create_app

from .conftest import NOW


@pytest.fixture
def app(conn, db_path):
    app = create_app(db_path=db_path, now_fn=lambda: NOW)

    # A tiny admin-only route so the role decorators can be tested on their own.
    @app.get("/test/admin-only")
    @auth.role_required("admin")
    def admin_only():
        return jsonify({"ok": True})

    @app.get("/test/logged-in")
    @auth.login_required
    def logged_in():
        return jsonify({"ok": True})

    return app


@pytest.fixture
def client(app):
    return app.test_client()


def register(client, username="sam", password="password123"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_register_creates_logged_in_rider_with_hashed_password(client, conn):
    res = register(client)
    assert res.status_code == 201
    user = res.get_json()["user"]
    assert user["username"] == "sam" and user["role"] == "rider"
    assert set(user) == {"id", "username", "role"}

    row = conn.execute("SELECT password_hash, created_at FROM users WHERE username = 'sam'").fetchone()
    assert row["password_hash"] != "password123"
    assert "password123" not in row["password_hash"]
    assert row["created_at"] == NOW.isoformat()

    assert client.get("/api/auth/me").get_json()["user"] == user


def test_register_ignores_role_in_body(client):
    res = client.post("/api/auth/register",
                      json={"username": "sneaky", "password": "password123", "role": "admin"})
    assert res.status_code == 201
    assert res.get_json()["user"]["role"] == "rider"


def test_duplicate_username_returns_409(client):
    assert register(client).status_code == 201
    res = register(client, password="different-pass")
    assert res.status_code == 409
    assert "error" in res.get_json()


@pytest.mark.parametrize("username,password", [
    ("sam", "short"),            # password under 8 characters
    ("ab", "password123"),       # username too short
    ("a" * 31, "password123"),   # username too long
    ("bad name", "password123"),  # space not allowed
    ("bad-name", "password123"),  # dash not allowed
    (None, "password123"),
    ("sam", None),
    (123, "password123"),
])
def test_bad_register_input_returns_400(client, username, password):
    res = register(client, username, password)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_register_without_json_returns_400(client):
    assert client.post("/api/auth/register", data="not json").status_code == 400


def test_wrong_password_and_unknown_user_get_same_401(client):
    register(client)
    client.post("/api/auth/logout")
    wrong_pw = login(client, "sam", "nope-nope-nope")
    unknown = login(client, "nobody", "password123")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.get_json() == unknown.get_json() == {"error": "Wrong username or password"}


def test_login_then_me_then_logout(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").get_json() == {"user": None}

    res = login(client, "sam", "password123")
    assert res.status_code == 200
    user = res.get_json()["user"]
    assert user["username"] == "sam"
    assert client.get("/api/auth/me").get_json() == {"user": user}

    out = client.post("/api/auth/logout")
    assert out.status_code == 200 and out.get_json() == {"ok": True}
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json() == {"user": None}


def test_me_never_401_when_logged_out(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.get_json() == {"user": None}


def test_login_replaces_previous_session(client, conn):
    auth.create_user(conn, "other", "password123")
    register(client)
    login(client, "other", "password123")
    assert client.get("/api/auth/me").get_json()["user"]["username"] == "other"


def test_session_cookie_is_httponly_and_lax(client):
    res = register(client)
    cookie = res.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_role_required_401_logged_out_403_for_rider_200_for_admin(client, conn):
    assert client.get("/test/admin-only").status_code == 401

    register(client)  # a rider
    res = client.get("/test/admin-only")
    assert res.status_code == 403
    assert "error" in res.get_json()

    auth.create_user(conn, "boss", "password123", role="admin")
    login(client, "boss", "password123")
    assert client.get("/test/admin-only").status_code == 200


def test_login_required(client):
    assert client.get("/test/logged-in").status_code == 401
    register(client)
    assert client.get("/test/logged-in").status_code == 200


def test_check_login_and_create_user_helpers(conn):
    user = auth.create_user(conn, "helper", "password123", role="analyst")
    assert user["role"] == "analyst"
    assert auth.check_login(conn, "helper", "password123") == user
    assert auth.check_login(conn, "helper", "wrong-password") is None
    assert auth.check_login(conn, "ghost", "password123") is None
    with pytest.raises(auth.UsernameTaken):
        auth.create_user(conn, "helper", "password123")
    with pytest.raises(ValueError):
        auth.create_user(conn, "bad_role", "password123", role="superuser")


def test_seed_demo_users_is_idempotent(conn):
    assert auth.seed_demo_users(conn) == 3
    assert auth.seed_demo_users(conn) == 0
    roles = dict(conn.execute("SELECT username, role FROM users").fetchall())
    assert roles == {"rider_demo": "rider", "analyst_demo": "analyst", "admin_demo": "admin"}
    for username in roles:
        assert auth.check_login(conn, username, "demo-password") is not None
