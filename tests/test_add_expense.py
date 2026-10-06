"""Expense creation requirements, using isolated SQLite databases."""

import importlib
import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

import pytest

from database import db, queries


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "expenses.db")
    monkeypatch.setenv("SECRET_KEY", "expense-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    application = importlib.import_module("app").app
    db.init_db()
    db.seed_db()
    for key, value in {
        "TESTING": True, "SECRET_KEY": "expense-test-secret",
        "SESSION_COOKIE_SECURE": False,
    }.items():
        monkeypatch.setitem(application.config, key, value)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class FormParser(HTMLParser):
    def __init__(self, response, action="/expenses/add"):
        super().__init__()
        self.action = action
        self.active = False
        self.fields = {}
        self.options = []
        self.labels = []
        self.forms = []
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.forms.append(attrs)
            self.active = attrs.get("action") == self.action
        if self.active:
            if tag in ("input", "select", "textarea"):
                self.fields[attrs["name"]] = attrs
            if tag == "option":
                self.options.append(attrs)
            if tag == "label":
                self.labels.append(attrs["for"])

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def login(client, email="demo@spendly.com", password="demo123"):
    token = FormParser(client.get("/login"), "/login").fields[
        "csrf_token"]["value"]
    response = client.post("/login", data={
        "email": email, "password": password, "csrf_token": token,
    })
    assert response.status_code == 302
    return token


def submit(client, **changes):
    token = FormParser(client.get("/expenses/add")).fields[
        "csrf_token"]["value"]
    data = {
        "amount": "12.50", "category": "Food", "date": "2024-02-29",
        "description": "Lunch", "csrf_token": token,
    }
    data.update(changes)
    data = {key: value for key, value in data.items() if value is not None}
    return client.post("/expenses/add", data=data)


def snapshot():
    with closing(db.get_db()) as connection:
        return {
            table: [tuple(row) for row in connection.execute(
                "SELECT * FROM " + table + " ORDER BY id",
            )] for table in ("users", "expenses")
        }


def newest():
    with closing(db.get_db()) as connection:
        return dict(connection.execute(
            "SELECT * FROM expenses ORDER BY id DESC LIMIT 1",
        ).fetchone())


def test_form_defaults_and_read_only_navigation(client):
    login(client)
    before = snapshot()
    response = client.get("/expenses/add")
    assert response.status_code == 200
    form = FormParser(response)
    assert [item["action"] for item in form.forms] == [
        "/logout", "/expenses/add",
    ]
    assert all(item["method"] == "POST" for item in form.forms)
    assert form.fields["amount"]["value"] == ""
    assert form.fields["amount"]["type"] == "number"
    assert form.fields["amount"]["min"] == "0.01"
    assert form.fields["amount"]["max"] == "999999999.99"
    assert form.fields["amount"]["step"] == "0.01"
    assert form.fields["category"]["id"] == "category"
    assert form.fields["date"]["type"] == "date"
    assert form.fields["date"]["value"] == date.today().isoformat()
    assert form.fields["description"]["maxlength"] == "500"
    assert form.fields["csrf_token"]["type"] == "hidden"
    assert form.fields["csrf_token"]["value"]
    assert all("required" in form.fields[field]
               for field in ("amount", "category", "date"))
    assert "required" not in form.fields["description"]
    assert form.labels == ["amount", "category", "date", "description"]
    assert all(form.fields[field]["id"] == field for field in form.labels)
    assert [option["value"] for option in form.options] == [
        "", "Food", "Transport", "Bills", "Health", "Entertainment",
        "Shopping", "Other",
    ]
    assert "selected" in form.options[0]
    assert b'type="submit">Save expense</button>' in response.data
    assert b"(optional)" in response.data
    assert b'href="/profile">Cancel</a>' in response.data
    assert client.head("/expenses/add").status_code == 200
    for path in ("/profile", "/profile?start_date=invalid"):
        assert b'href="/expenses/add"' in client.get(path).data
    assert client.get("/static/css/expense.css").status_code == 200
    assert snapshot() == before


@pytest.mark.parametrize("identity", [None, True, "1", 0, -1, 2 ** 63, 999999])
@pytest.mark.parametrize("method", ["get", "head", "post"])
def test_unauthenticated_and_invalid_identity(client, identity, method):
    if identity is not None:
        with client.session_transaction() as session:
            session["user_id"] = identity
    before = snapshot()
    response = getattr(client, method)("/expenses/add")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert snapshot() == before


def test_deleted_identity(client):
    user_id = db.create_user("Deleted", "deleted@example.com", "password123")
    login(client, "deleted@example.com", "password123")
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    before = snapshot()
    assert client.post("/expenses/add").headers["Location"] == "/login"
    assert client.get("/expenses/add").headers["Location"] == "/login"
    assert snapshot() == before


def test_anonymous_invalid_post_redirects_before_validation(client):
    before = snapshot()
    response = client.post("/expenses/add?user_id=1", data={
        "amount": "invalid", "category": "Unknown", "date": "not-a-date",
        "user_id": "1", "csrf_token": "incorrect",
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert snapshot() == before


@pytest.mark.parametrize("field,value", [
    ("amount", value) for value in (
        None, "", " ", "0", "-1", "+1", "1e2", "NaN", "Infinity",
        "1,000", "₹1", "12.345", "1000000000", ".50", "12.", "１２",
    )
] + [
    ("category", value) for value in (None, "", "Unknown", "food", " Food ")
] + [
    ("date", value) for value in (
        None, "", "2023-02-29", "2024-04-31", "2024-2-01", "0000-01-01",
        "2024-01-01T12:00:00", " 2024-01-01 ", "２０２４-01-01",
    )
] + [("description", "x" * 501)])
def test_invalid_fields_do_not_write(client, field, value):
    login(client)
    before = snapshot()
    response = submit(client, **{field: value})
    assert response.status_code == 400
    form = FormParser(response)
    assert form.fields[field]["aria-invalid"] == "true"
    assert field + "-error" in form.fields[field]["aria-describedby"]
    if field == "date":
        assert form.fields[field]["value"] == (value or "")
    assert snapshot() == before


@pytest.mark.parametrize("amount", [
    "0.01", "12", "12.5", "12.50", "999999999.99", " 12.50 ", "00012.50",
])
def test_valid_amounts(client, amount):
    login(client)
    assert submit(client, amount=amount).status_code == 302
    assert newest()["amount"] == float(Decimal(amount.strip()))


@pytest.mark.parametrize("category", [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping",
    "Other",
])
def test_each_category(client, category):
    login(client)
    assert submit(client, category=category).status_code == 302
    assert newest()["category"] == category


@pytest.mark.parametrize("expense_date", [
    "0001-01-01", "2024-02-29", date.today().isoformat(), "9999-12-31",
])
def test_valid_dates(client, expense_date):
    login(client)
    assert submit(client, date=expense_date).status_code == 302
    assert newest()["date"] == expense_date


@pytest.mark.parametrize("description,expected", [
    (None, None), ("", None), (" \t ", None), ("  Lunch  ", "Lunch"),
    (" " + "x" * 500 + " ", "x" * 500),
])
def test_description_normalization(client, description, expected):
    login(client)
    assert submit(client, description=description).status_code == 302
    assert newest()["description"] == expected


def test_errors_preserve_and_escape_values(client):
    login(client)
    payload = '\"><script>alert("expense")</script>'
    response = submit(client, amount=payload, description=payload)
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert payload not in html and "&lt;script&gt;" in html
    form = FormParser(response)
    assert form.fields["amount"]["value"] == payload
    assert form.fields["date"]["value"] == "2024-02-29"
    assert next(item["value"] for item in form.options
                if "selected" in item) == "Food"
    response = submit(client, description=payload, date=date.today().isoformat())
    assert response.status_code == 302
    assert newest()["description"] == payload
    html = client.get("/profile").get_data(as_text=True)
    assert payload not in html and "&lt;script&gt;" in html


def test_multiple_field_errors_do_not_add_unknown_category(client):
    login(client)
    before = snapshot()
    response = submit(client, amount="", category="NotListed",
                      date="2024-2-01", description="x" * 501)
    assert response.status_code == 400
    assert b'role="alert"' in response.data
    form = FormParser(response)
    for field in ("amount", "category", "date", "description"):
        assert form.fields[field]["aria-invalid"] == "true"
        assert field + "-error" in form.fields[field]["aria-describedby"]
        assert ('id="{}-error"'.format(field)).encode() in response.data
    assert form.fields["date"]["value"] == "2024-2-01"
    assert [option["value"] for option in form.options] == [
        "", "Food", "Transport", "Bills", "Health", "Entertainment",
        "Shopping", "Other",
    ]
    assert "selected" in form.options[0]
    assert snapshot() == before


def test_csrf_rejection_and_logout_remain_functional(client, flask_app):
    old_token = login(client)
    other = flask_app.test_client()
    login(other)
    foreign_token = FormParser(other.get("/expenses/add")).fields[
        "csrf_token"]["value"]
    before = snapshot()
    for token in (None, "", "wrong", "évil", old_token, foreign_token):
        response = submit(client, csrf_token=token, description="Keep this")
        assert response.status_code == 400
        assert b"Your form has expired." in response.data
        assert b"Keep this" in response.data
    assert snapshot() == before
    page = client.get("/expenses/add")
    token = FormParser(page, "/logout").fields["csrf_token"]["value"]
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert client.get("/expenses/add").headers["Location"] == "/login"


def test_success_commit_profile_and_refresh(client):
    login(client)
    before = snapshot()
    response = submit(client, description="New lunch", date="9999-12-31")
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    row = newest()
    assert row["id"] > before["expenses"][-1][0]
    assert row["created_at"]
    assert row["user_id"] == db.get_user_by_email("demo@spendly.com")["id"]
    after = snapshot()
    assert after["users"] == before["users"]
    assert after["expenses"][:-1] == before["expenses"]
    profile = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "Expense added successfully." in profile
    assert 'role="status"' in profile
    assert "₹248.00" in profile and "New lunch" in profile
    assert "Expense added successfully." not in client.get(
        "/profile").get_data(as_text=True)
    assert snapshot() == after
    assert submit(client).status_code == 302
    assert len(snapshot()["expenses"]) == len(after["expenses"]) + 1


def test_user_isolation_and_filtered_latest_ten(client, flask_app):
    user_id = db.create_user("Other", "other@example.com", "password123")
    login(client, "other@example.com", "password123")
    assert b'href="/expenses/add"' in client.get("/profile").data
    token = FormParser(client.get("/expenses/add")).fields[
        "csrf_token"]["value"]
    for index in range(11):
        response = client.post("/expenses/add?user_id=1", data={
            "amount": "1.00", "category": "Food", "date": "2024-05-01",
            "description": "Purchase {:02d}".format(index), "user_id": "1",
            "csrf_token": token,
        })
        assert response.status_code == 302
        assert newest()["user_id"] == user_id
    assert submit(client, date="2020-01-01", description="Older", amount="2",
                  category="Other").status_code == 302
    html = client.get("/profile").get_data(as_text=True)
    assert "₹13.00" in html and "Older" not in html
    assert "Purchase 00" not in html
    assert html.index("Purchase 10") < html.index("Purchase 09")
    summary = queries.get_summary_stats(user_id)
    assert summary == {
        "total_spent": Decimal("13.00"), "transaction_count": 12,
        "top_category": "Food",
    }
    assert queries.get_category_breakdown(user_id) == [
        {"name": "Food", "amount": Decimal("11.00"), "pct": 85},
        {"name": "Other", "amount": Decimal("2.00"), "pct": 15},
    ]
    filtered = client.get(
        "/profile?start_date=2020-01-01&end_date=2020-01-01",
    ).get_data(as_text=True)
    assert "Older" in filtered and "Purchase" not in filtered
    empty = client.get("/profile?start_date=2025-01-01").get_data(as_text=True)
    assert "No expenses in this date range." in empty
    demo = flask_app.test_client()
    login(demo)
    html = demo.get("/profile?user_id={}".format(user_id)).get_data(as_text=True)
    assert "Purchase" not in html and "₹235.50" in html


def test_helper_commit_rollback_and_closure(flask_app, monkeypatch):
    user_id = db.get_user_by_email("demo@spendly.com")["id"]
    original_get_db = db.get_db
    opened = []

    def tracked_connection():
        connection = original_get_db()
        opened.append(connection)
        return connection

    monkeypatch.setattr(db, "get_db", tracked_connection)
    expense_id = db.create_expense(user_id, 1, "Food", "2024-01-01")
    assert newest()["id"] == expense_id
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    before = snapshot()
    with pytest.raises(sqlite3.IntegrityError):
        db.create_expense(999999, 1, "Food", "2024-01-01")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")
    assert snapshot() == before

    class FailingCommit(sqlite3.Connection):
        def __exit__(self, *args):
            super().__exit__(RuntimeError, RuntimeError("commit failed"), None)
            raise RuntimeError("commit failed")

    def failing_connection():
        connection = sqlite3.connect(db.DB_PATH, factory=FailingCommit)
        connection.execute("PRAGMA foreign_keys = ON")
        opened.append(connection)
        return connection

    monkeypatch.setattr(db, "get_db", failing_connection)
    with pytest.raises(RuntimeError, match="commit failed"):
        db.create_expense(user_id, 1, "Food", "2024-01-01")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")
    monkeypatch.setattr(db, "get_db", original_get_db)
    assert snapshot() == before


def test_route_database_failure_is_not_success(client, monkeypatch):
    login(client)
    before = snapshot()

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("storage unavailable")

    monkeypatch.setattr(importlib.import_module("app"), "create_expense",
                        unavailable)
    with pytest.raises(sqlite3.OperationalError, match="storage unavailable"):
        submit(client)
    with client.session_transaction() as session:
        assert "_flashes" not in session
    assert snapshot() == before
