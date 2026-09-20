"""Registration coverage using isolated, file-backed SQLite databases."""

import importlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from html.parser import HTMLParser
from threading import Event, Lock

import pytest
from werkzeug.security import check_password_hash

from database import db


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    # App import initializes/seeds SQLite, so select the test database first.
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "registration.db")
    application = importlib.import_module("app").app
    # Cached app imports do not repeat startup for subsequent test databases.
    db.init_db()
    db.seed_db()
    monkeypatch.setitem(application.config, "TESTING", True)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def valid_form():
    return {
        "name": "  New User  ",
        "email": "  New.User@Example.COM  ",
        "password": "registration-secret-42",
        "confirm_password": "registration-secret-42",
    }


def snapshot():
    with closing(db.get_db()) as connection:
        users = connection.execute(
            "SELECT * FROM users ORDER BY id"
        ).fetchall()
        expenses = connection.execute(
            "SELECT * FROM expenses ORDER BY id"
        ).fetchall()
    return [dict(row) for row in users], [dict(row) for row in expenses]


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


def test_registration_form(client):
    response = client.get("/register")
    form = FormParser(response)
    assert response.status_code == 200
    assert form.forms == [{"method": "POST", "action": "/register"}]
    assert set(form.inputs) == {"name", "email", "password", "confirm_password"}
    assert form.inputs["name"]["value"] == ""
    assert form.inputs["email"]["value"] == ""
    assert form.inputs["password"]["minlength"] == "8"
    assert "value" not in form.inputs["password"]
    assert form.inputs["confirm_password"]["type"] == "password"
    assert "required" in form.inputs["confirm_password"]
    assert "value" not in form.inputs["confirm_password"]


def test_head_registration_preserves_get_status(client):
    baseline = snapshot()
    response = client.head("/register")
    assert response.status_code == 200
    assert response.data == b""
    assert snapshot() == baseline


def test_success_persists_user_and_redirects_without_session(
    client, valid_form,
):
    baseline_users, baseline_expenses = snapshot()
    response = client.post("/register", data=valid_form)
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert not response.headers.getlist("Set-Cookie")

    users, expenses = snapshot()
    assert users[:-1] == baseline_users
    assert expenses == baseline_expenses
    assert len(users) == len(baseline_users) + 1
    user = users[-1]
    assert user["id"] > baseline_users[-1]["id"]
    assert user["name"] == "New User"
    assert user["email"] == "new.user@example.com"
    datetime.strptime(user["created_at"], "%Y-%m-%d %H:%M:%S")
    assert user["password_hash"] != valid_form["password"]
    assert check_password_hash(user["password_hash"], valid_form["password"])
    assert not check_password_hash(user["password_hash"], "incorrect-password")

    for _ in range(2):
        login = client.get(response.headers["Location"])
        assert login.status_code == 200
        assert b"Sign in to your Spendly account" in login.data
        assert not login.headers.getlist("Set-Cookie")
    assert snapshot() == (users, expenses)


@pytest.mark.parametrize("password", ["12345678", "  secret phrase  "])
def test_password_boundary_and_spaces(client, valid_form, password):
    valid_form["password"] = password
    valid_form["confirm_password"] = password
    assert client.post("/register", data=valid_form).status_code == 302
    stored_hash = snapshot()[0][-1]["password_hash"]
    assert check_password_hash(stored_hash, password)
    if password != password.strip():
        assert not check_password_hash(stored_hash, password.strip())


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("name", None, "Please enter your name."),
        ("name", "", "Please enter your name."),
        ("name", " \t\n ", "Please enter your name."),
        ("email", None, "Please enter a valid email address."),
        ("email", "", "Please enter a valid email address."),
        ("email", "no-at-sign", "Please enter a valid email address."),
        ("email", "a@@example.com", "Please enter a valid email address."),
        ("email", "@example.com", "Please enter a valid email address."),
        ("email", "user@", "Please enter a valid email address."),
        ("email", "a b@example.com", "Please enter a valid email address."),
        ("email", "a@exa\tmple.com", "Please enter a valid email address."),
        ("email", "a@b\u2003c.com", "Please enter a valid email address."),
        ("password", None, "Password must be at least 8 characters."),
        ("password", "", "Password must be at least 8 characters."),
        ("password", "1234567", "Password must be at least 8 characters."),
        ("confirm_password", None, "Please confirm your password."),
        ("confirm_password", "", "Please confirm your password."),
    ],
)
def test_invalid_input(client, valid_form, field, value, message, monkeypatch):
    baseline = snapshot()
    if value is None:
        valid_form.pop(field)
    else:
        valid_form[field] = value

    def unexpected_creation(*args):
        pytest.fail("Invalid input must not reach the database helper")

    monkeypatch.setattr(importlib.import_module("app"), "create_user",
                        unexpected_creation)
    response = client.post("/register", data=valid_form)
    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert snapshot() == baseline
    form = FormParser(response)
    assert form.inputs["name"]["value"] == valid_form.get("name", "")
    assert form.inputs["email"]["value"] == valid_form.get("email", "")
    assert "value" not in form.inputs["password"]
    assert "value" not in form.inputs["confirm_password"]


@pytest.mark.parametrize(
    "confirmation",
    [
        "different-password",
        "REGISTRATION-SECRET-42",
        " registration-secret-42 ",
    ],
)
def test_mismatched_passwords_do_not_create_user(
    client, valid_form, confirmation, monkeypatch,
):
    baseline = snapshot()
    valid_form["confirm_password"] = confirmation

    def unexpected_creation(*args):
        pytest.fail("Mismatched passwords must not reach the database helper")

    monkeypatch.setattr(importlib.import_module("app"), "create_user",
                        unexpected_creation)
    response = client.post("/register", data=valid_form)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Passwords do not match." in html
    assert snapshot() == baseline
    form = FormParser(response)
    assert form.inputs["name"]["value"] == valid_form["name"]
    assert form.inputs["email"]["value"] == valid_form["email"]
    for field in ("password", "confirm_password"):
        assert "value" not in form.inputs[field]
        assert valid_form[field] not in html


def test_first_validation_error(client):
    response = client.post("/register", data={})
    assert response.status_code == 400
    assert b"Please enter your name." in response.data
    assert b"Please enter a valid email address." not in response.data


@pytest.mark.parametrize(
    "email", ["user@localhost", "\u00c9lodie@Example.com"]
)
def test_email_format_does_not_add_restrictions(client, valid_form, email):
    valid_form["email"] = email
    assert client.post("/register", data=valid_form).status_code == 302
    assert snapshot()[0][-1]["email"] == email.lower()


@pytest.mark.parametrize(
    "email", ["demo@spendly.com", "DEMO@SPENDLY.COM", "  Demo@Spendly.Com  "]
)
def test_existing_email_is_rejected(client, valid_form, email):
    baseline = snapshot()
    valid_form["email"] = email
    response = client.post("/register", data=valid_form)
    assert response.status_code == 409
    assert b"An account with this email already exists." in response.data
    assert snapshot() == baseline
    form = FormParser(response)
    assert form.inputs["name"]["value"] == valid_form["name"]
    assert form.inputs["email"]["value"] == email
    assert "value" not in form.inputs["password"]
    assert "value" not in form.inputs["confirm_password"]
    assert valid_form["password"] not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "email", ["Legacy@Example.COM", "\u00c9LODIE@Example.COM"]
)
def test_legacy_mixed_case_email(client, valid_form, email):
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES (?, ?, ?)",
                ("Legacy User", email, "untouched-legacy-hash"),
            )
    baseline = snapshot()
    valid_form["email"] = email.lower()
    assert client.post("/register", data=valid_form).status_code == 409
    assert snapshot() == baseline


def test_repeated_submission(client, valid_form):
    assert client.post("/register", data=valid_form).status_code == 302
    baseline = snapshot()
    assert client.post("/register", data=valid_form).status_code == 409
    assert snapshot() == baseline


def test_error_redisplay_escapes_html_and_omits_password(client, valid_form):
    valid_form.update(name='<script>alert("name")</script>',
                      email='"><script>alert("email")</script>')
    response = client.post("/register", data=valid_form)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "&lt;script&gt;" in html
    assert valid_form["name"] not in html
    assert valid_form["email"] not in html
    assert valid_form["password"] not in html
    form = FormParser(response)
    assert form.inputs["name"]["value"] == valid_form["name"]
    assert form.inputs["email"]["value"] == valid_form["email"]
    assert "value" not in form.inputs["password"]
    assert "value" not in form.inputs["confirm_password"]


def test_create_user_returns_committed_id(flask_app):
    user_id = db.create_user(
        "O'Brien", "obrien@example.com", "helper-password"
    )
    user = snapshot()[0][-1]
    assert user["id"] == user_id
    assert user["name"] == "O'Brien"
    with pytest.raises(db.DuplicateEmailError):
        db.create_user("Other Name", "obrien@example.com", "other-password")


def test_unrelated_database_failure_propagates_and_rolls_back(
    client, valid_form,
):
    baseline = snapshot()
    with closing(db.get_db()) as connection:
        with connection:
            # FAIL keeps trigger side effects until the transaction rolls back.
            connection.execute(
                """
                CREATE TRIGGER fail_registration BEFORE INSERT ON users
                BEGIN
                    UPDATE users SET name = 'must be rolled back';
                    SELECT RAISE(FAIL, 'registration storage failure');
                END
                """
            )
    with pytest.raises(
        sqlite3.IntegrityError, match="registration storage failure"
    ):
        client.post("/register", data=valid_form)
    assert snapshot() == baseline
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DROP TRIGGER fail_registration")
    assert client.post("/register", data=valid_form).status_code == 302


def test_concurrent_registrations_create_one_user(
    flask_app, valid_form, monkeypatch,
):
    baseline_users, baseline_expenses = snapshot()
    original_get_db = db.get_db
    first_locked = Event()
    second_attempting = Event()
    release_first = Event()
    counter_lock = Lock()
    connection_count = 0

    class CoordinatedConnection:
        def __init__(self, connection, number):
            self.connection = connection
            self.number = number

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, *args):
            return self.connection.__exit__(*args)

        def close(self):
            self.connection.close()

        def execute(self, sql, parameters=()):
            if sql == "BEGIN IMMEDIATE" and self.number == 2:
                second_attempting.set()
            cursor = self.connection.execute(sql, parameters)
            if sql == "BEGIN IMMEDIATE" and self.number == 1:
                first_locked.set()
                assert release_first.wait(3), "Transaction was not released"
            return cursor

    def coordinated_get_db():
        nonlocal connection_count
        with counter_lock:
            connection_count += 1
            number = connection_count
        return CoordinatedConnection(original_get_db(), number)

    def submit(email):
        with flask_app.test_client() as thread_client:
            return thread_client.post(
                "/register", data=dict(valid_form, email=email)
            ).status_code

    with monkeypatch.context() as patch:
        patch.setattr(db, "get_db", coordinated_get_db)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(submit, "Concurrent@Example.com")
            try:
                assert first_locked.wait(3), "First request did not lock"
                second = pool.submit(submit, "  CONCURRENT@example.COM  ")
                assert second_attempting.wait(3), "Second request did not start"
            finally:
                release_first.set()
            assert first.result(timeout=10) == 302
            assert second.result(timeout=10) == 409

    users, expenses = snapshot()
    assert users[:-1] == baseline_users
    assert expenses == baseline_expenses
    assert len(users) == len(baseline_users) + 1
    assert users[-1]["email"] == "concurrent@example.com"
