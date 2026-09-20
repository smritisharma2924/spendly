"""Authentication coverage with isolated databases and real form tokens."""

import importlib
import os
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import sys

import pytest
from flask import message_flashed
from werkzeug.security import generate_password_hash

from database import db


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setenv("SECRET_KEY", "auth-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    application = importlib.import_module("app").app
    db.init_db()
    db.seed_db()
    for key, value in {
        "TESTING": True, "SECRET_KEY": "auth-test-secret",
        "SESSION_COOKIE_SECURE": False,
    }.items():
        monkeypatch.setitem(application.config, key, value)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class FormParser(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.inputs = {}
        self.forms = []
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input":
            self.inputs[attributes["name"]] = attributes
        elif tag == "form":
            self.forms.append(attributes)


def token(client):
    return FormParser(client.get("/login")).inputs["csrf_token"]["value"]


def login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={
        "email": email, "password": password, "csrf_token": token(client),
    })


def session_data(client):
    with client.session_transaction() as current:
        return dict(current)


def snapshot():
    with closing(db.get_db()) as connection:
        return (
            [tuple(row) for row in connection.execute("SELECT * FROM users")],
            [tuple(row)
             for row in connection.execute("SELECT * FROM expenses")],
        )


def test_anonymous_forms_and_public_pages(client, monkeypatch):
    def unexpected_lookup(user_id):
        pytest.fail("Anonymous requests should not look up users")

    monkeypatch.setattr(importlib.import_module("app"), "get_user_by_id",
                        unexpected_lookup)
    for path in ("/", "/terms", "/privacy", "/register"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"Get started" in response.data
        assert b'action="/logout"' not in response.data
        assert not response.headers.getlist("Set-Cookie")
    response = client.get("/login")
    form = FormParser(response)
    assert response.status_code == 200
    assert form.forms == [{"method": "POST", "action": "/login"}]
    assert form.inputs["email"]["value"] == ""
    assert form.inputs["email"]["autocomplete"] == "email"
    assert form.inputs["password"]["autocomplete"] == "current-password"
    assert "minlength" not in form.inputs["password"]
    assert "value" not in form.inputs["password"]
    assert set(session_data(client)) == {"csrf_token"}
    assert client.head("/login").status_code == 200


def test_demo_login_session_and_logout(client, flask_app):
    baseline = snapshot()
    old_token = token(client)
    with client.session_transaction() as current:
        current["old_value"] = "discard"
        current.permanent = True
    response = client.post("/login?next=https://example.com", data={
        "email": "demo@spendly.com", "password": "demo123",
        "csrf_token": old_token, "next": "https://example.com",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    current = session_data(client)
    assert set(current) == {"user_id", "csrf_token"}
    assert type(current["user_id"]) is int
    assert current["csrf_token"] != old_token
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert "Secure" not in cookie and "Expires" not in cookie
    signed_cookie = client.get_cookie("session").value
    decoded = flask_app.session_interface.get_signing_serializer(
        flask_app,
    ).loads(signed_cookie)
    assert decoded == current
    for path in ("/", "/terms", "/privacy"):
        page = client.get(path)
        assert b"Demo User" in page.data
        form = FormParser(page)
        assert form.forms[0]["method"] == "POST"
        assert form.forms[0]["action"] == "/logout"
        assert form.inputs["csrf_token"]["value"] == current["csrf_token"]
    assert b'action="/logout"' not in flask_app.test_client().get("/").data
    response = client.post(
        "/logout", data={"csrf_token": current["csrf_token"]},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert session_data(client) == {}
    assert b"Get started" in client.get("/").data
    assert snapshot() == baseline


@pytest.mark.parametrize("email", [
    "DEMO@SPENDLY.COM", "  Demo@Spendly.Com  ",
])
def test_normalized_email(client, email):
    assert login(client, email=email).status_code == 302


@pytest.mark.parametrize("email", ["ÉLODIE@Example.COM", "User@localhost"])
def test_legacy_email_and_ambiguous_matches(client, email):
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES (?, ?, ?)",
                ("Legacy", email, generate_password_hash("legacy-password")),
            )
    assert login(client, email.lower(), "legacy-password").status_code == 302
    current = session_data(client)
    client.post("/logout", data={"csrf_token": current["csrf_token"]})
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES (?, ?, ?)",
                ("Ambiguous", email.lower(), generate_password_hash("other")),
            )
    baseline = snapshot()
    assert db.get_user_by_email(email.lower()) is None
    response = login(client, email.lower(), "legacy-password")
    assert response.status_code == 401
    assert b"Invalid email or password." in response.data
    assert "user_id" not in session_data(client)
    assert snapshot() == baseline


def test_registration_then_login_exact_password_and_escaped_name(client):
    name = '<script>alert("name")</script>'
    password = "  exact secret  "
    response = client.post("/register", data={
        "name": name, "email": "new@example.com", "password": password,
        "confirm_password": password,
    })
    assert response.status_code == 302
    assert "user_id" not in session_data(client)
    rejected = login(client, "new@example.com", password.strip())
    assert rejected.status_code == 401
    assert login(client, "new@example.com", password).status_code == 302
    page = client.get("/").get_data(as_text=True)
    assert name not in page
    assert "&lt;script&gt;" in page
    assert password not in page


@pytest.mark.parametrize("field,value,message", [
    ("email", None, "Please enter a valid email address."),
    ("email", "", "Please enter a valid email address."),
    ("email", " \t ", "Please enter a valid email address."),
    ("email", "missing-at", "Please enter a valid email address."),
    ("email", "@example.com", "Please enter a valid email address."),
    ("email", "a@", "Please enter a valid email address."),
    ("email", "a@@b", "Please enter a valid email address."),
    ("email", "a@b\u2003c", "Please enter a valid email address."),
    ("password", None, "Please enter your password."),
    ("password", "", "Please enter your password."),
])
def test_invalid_fields(client, field, value, message, monkeypatch):
    baseline = snapshot()
    data = {"email": "demo@spendly.com", "password": "demo123",
            "csrf_token": token(client)}
    if value is None:
        del data[field]
    else:
        data[field] = value

    def unexpected_lookup(email):
        pytest.fail("Invalid fields must not reach credential lookup")

    monkeypatch.setattr(importlib.import_module("app"), "get_user_by_email",
                        unexpected_lookup)
    response = client.post("/login", data=data)
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    form = FormParser(response)
    assert form.inputs["email"]["value"] == data.get("email", "")
    assert "value" not in form.inputs["password"]
    assert "user_id" not in session_data(client)
    assert snapshot() == baseline


def test_credentials_have_same_error_and_email_is_escaped(client):
    baseline = snapshot()
    responses = [
        login(client, "demo@spendly.com", "wrong-password"),
        login(client, "missing@example.com", "wrong-password"),
    ]
    for response in responses:
        assert response.status_code == 401
        assert b"Invalid email or password." in response.data
        assert b"wrong-password" not in response.data
        assert "user_id" not in session_data(client)
    email = '\"><script>alert("email")</script>'
    response = login(client, email, "never-reflect-this-password")
    assert response.status_code == 400
    assert email not in response.get_data(as_text=True)
    assert b"&lt;script&gt;" in response.data
    assert b"never-reflect-this-password" not in response.data
    assert FormParser(response).inputs["email"]["value"] == email
    assert snapshot() == baseline


@pytest.mark.parametrize("email,password", [
    ("demo@spendly.com", "incorrect-password"),
    ("unregistered@example.com", "demo123"),
])
def test_credential_errors_flash_once_on_login_page(
    client, flask_app, email, password,
):
    messages = []

    def capture_message(sender, message, category, **extra):
        messages.append((category, message))

    with message_flashed.connected_to(capture_message, flask_app):
        response = login(client, email, password)
    assert response.status_code == 401
    assert response.request.path == "/login"
    assert "Location" not in response.headers
    assert messages == [("error", "Invalid email or password.")]
    assert response.data.count(b"Invalid email or password.") == 1
    current = session_data(client)
    assert "user_id" not in current
    assert "_flashes" not in current
    assert b"Invalid email or password." not in client.get("/login").data


@pytest.mark.parametrize("path", ["/login", "/logout"])
@pytest.mark.parametrize("bad_token", [None, "", "incorrect", "évil-token"])
@pytest.mark.parametrize("authenticated", [False, True])
def test_csrf_rejection_preserves_identity(
    client, path, bad_token, authenticated,
):
    if authenticated:
        assert login(client).status_code == 302
    else:
        token(client)
    before = session_data(client)
    data = {"email": "demo@spendly.com", "password": "demo123"}
    if bad_token is not None:
        data["csrf_token"] = bad_token
    assert client.post(path, data=data).status_code == 400
    assert session_data(client) == before


def test_cross_client_and_rotated_tokens(client, flask_app):
    foreign_token = token(flask_app.test_client())
    old_token = token(client)
    data = {"email": "demo@spendly.com", "password": "demo123",
            "csrf_token": foreign_token}
    assert client.post("/login", data=data).status_code == 400
    assert "user_id" not in session_data(client)
    data["csrf_token"] = old_token
    assert client.post("/login", data=data).status_code == 302
    before = session_data(client)
    for invalid in (old_token, foreign_token):
        response = client.post("/logout", data={"csrf_token": invalid})
        assert response.status_code == 400
        assert session_data(client) == before


def test_first_post_without_session_cannot_authenticate(client):
    assert client.post("/login", data={
        "email": "demo@spendly.com", "password": "demo123",
        "csrf_token": "invented-token",
    }).status_code == 400
    assert "user_id" not in session_data(client)
    assert session_data(client)["csrf_token"] != "invented-token"


def test_authenticated_login_does_not_switch_accounts(client):
    db.create_user("Other", "other@example.com", "other-secret")
    assert login(client).status_code == 302
    before = session_data(client)
    for method in ("get", "head"):
        response = getattr(client, method)("/login?next=https://example.com")
        assert response.status_code == 302
        assert response.headers["Location"] == "/"
    response = client.post("/login", data={
        "email": "other@example.com", "password": "other-secret",
        "csrf_token": before["csrf_token"],
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert session_data(client) == before


def test_logout_methods_and_anonymous_logout(client):
    assert login(client).status_code == 302
    before = session_data(client)
    for method in ("get", "head"):
        assert getattr(client, method)("/logout").status_code == 405
        assert session_data(client) == before
    client.post("/logout", data={"csrf_token": before["csrf_token"]})
    response = client.post("/logout", data={"csrf_token": token(client)})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert session_data(client) == {}


@pytest.mark.parametrize("user_id", [
    None, True, False, "1", 1.0, [], {}, 0, -1, 2 ** 63, 999999,
])
def test_invalid_or_missing_user_clears_session(client, user_id):
    with client.session_transaction() as current:
        current.update(
            user_id=user_id, csrf_token="old-token", extra="discard",
        )
    response = client.get("/")
    assert response.status_code == 200
    assert b'action="/logout"' not in response.data
    assert session_data(client) == {}


def test_deleted_user_and_tampered_cookie(client):
    user_id = db.create_user("Temporary", "temp@example.com", "temp-secret")
    assert login(client, "temp@example.com", "temp-secret").status_code == 302
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    assert client.get("/").status_code == 200
    assert session_data(client) == {}
    assert login(client).status_code == 302
    cookie = client.get_cookie("session").value
    payload, signature = cookie.rsplit(".", 1)
    altered = ("A" if signature[0] != "A" else "B") + signature[1:]
    client.set_cookie("session", payload + "." + altered)
    page = client.get("/")
    assert page.status_code == 200
    assert b'action="/logout"' not in page.data
    assert "user_id" not in session_data(client)


def test_lookup_helpers_and_database_errors(flask_app, monkeypatch):
    user = db.get_user_by_email("demo@spendly.com")
    assert db.get_user_by_id(user["id"])["email"] == "demo@spendly.com"
    assert db.get_user_by_email("absent@example.com") is None
    assert db.get_user_by_id(999999) is None

    def unavailable():
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(db, "get_db", unavailable)
    with pytest.raises(RuntimeError, match="storage unavailable"):
        db.get_user_by_email("demo@spendly.com")


@pytest.mark.parametrize("secret,secure,expected_error", [
    (None, "false", "SECRET_KEY"), ("", "false", "SECRET_KEY"),
    ("configured-secret", "invalid", "SESSION_COOKIE_SECURE"),
    ("configured-secret", None, None),
    ("configured-secret", "false", None),
    ("configured-secret", "0", None),
    ("configured-secret", "TRUE", None),
    ("configured-secret", "1", None),
])
def test_startup_configuration(tmp_path, secret, secure, expected_error):
    environment = os.environ.copy()
    settings = (("SECRET_KEY", secret), ("SESSION_COOKIE_SECURE", secure))
    for key, value in settings:
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    database_path = tmp_path / "startup.db"
    script = """
import sys
from pathlib import Path
from database import db
db.DB_PATH = Path(sys.argv[1])
from app import app
with app.test_client() as client:
    response = client.get('/login', base_url='https://localhost')
    assert response.status_code == 200
    print(response.headers['Set-Cookie'])
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(database_path)],
        cwd=Path(__file__).resolve().parents[1], env=environment,
        capture_output=True, text=True, timeout=20,
    )
    if expected_error:
        assert result.returncode != 0
        assert expected_error in result.stderr
        assert not database_path.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert database_path.exists()
        assert "HttpOnly" in result.stdout and "SameSite=Lax" in result.stdout
        assert ("Secure" in result.stdout) == (secure in ("TRUE", "1"))
