"""Expense editing requirements against isolated SQLite databases."""

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
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "edit.db")
    monkeypatch.setenv("SECRET_KEY", "edit-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    application = importlib.import_module("app").app
    db.init_db()
    db.seed_db()
    for key, value in {
        "TESTING": True, "SECRET_KEY": "edit-test-secret",
        "SESSION_COOKIE_SECURE": False,
    }.items():
        monkeypatch.setitem(application.config, key, value)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def expense(flask_app):
    owner = db.get_user_by_email("demo@spendly.com")["id"]
    expense_id = db.create_expense(owner, 12.5, "Food", "2024-02-29", "Lunch")
    return dict(db.get_expense_by_id(expense_id, owner))


class PageParser(HTMLParser):
    def __init__(self, response, action=None):
        super().__init__()
        self.action = action
        self.active = False
        self.forms = []
        self.fields = {}
        self.options = []
        self.labels = []
        self.links = []
        self.description = ""
        self.in_description = False
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs)
        if tag == "form":
            self.forms.append(attrs)
            self.active = attrs.get("action") == self.action
        if self.active:
            if tag in ("input", "select", "textarea"):
                self.fields[attrs["name"]] = attrs
            if tag == "textarea":
                self.in_description = True
            if tag == "option":
                self.options.append(attrs)
            if tag == "label":
                self.labels.append(attrs["for"])

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False
        if tag == "textarea":
            self.in_description = False

    def handle_data(self, data):
        if self.in_description:
            self.description += data


def login(client, email="demo@spendly.com", password="demo123"):
    token = PageParser(client.get("/login"), "/login").fields[
        "csrf_token"]["value"]
    response = client.post("/login", data={
        "email": email, "password": password, "csrf_token": token,
    })
    assert response.status_code == 302
    return token


def edit_path(expense):
    return "/expenses/{}/edit".format(expense["id"])


def submit(client, expense, **changes):
    path = edit_path(expense)
    token = PageParser(client.get(path), path).fields["csrf_token"]["value"]
    data = {
        "amount": "15.75", "category": "Shopping", "date": "2025-01-01",
        "description": "Updated", "csrf_token": token,
    }
    data.update(changes)
    return client.post(path, data={k: v for k, v in data.items() if v is not None})


def snapshot():
    with closing(db.get_db()) as connection:
        return {
            table: [tuple(row) for row in connection.execute(
                "SELECT * FROM " + table + " ORDER BY id",
            )] for table in ("users", "expenses")
        }


def saved(expense):
    return dict(db.get_expense_by_id(expense["id"], expense["user_id"]))


def test_prefill_controls_and_read_only_navigation(client, expense):
    login(client)
    before = snapshot()
    path = edit_path(expense)
    response = client.get(path)
    assert response.status_code == 200
    page = PageParser(response, path)
    assert [form["action"] for form in page.forms] == ["/logout", path]
    assert all(form["method"] == "POST" for form in page.forms)
    assert page.fields["amount"]["value"] == "12.50"
    assert page.fields["amount"]["min"] == "0.01"
    assert page.fields["amount"]["max"] == "999999999.99"
    assert page.fields["amount"]["step"] == "0.01"
    assert page.fields["date"]["value"] == "2024-02-29"
    assert page.description == "Lunch"
    assert page.fields["description"]["maxlength"] == "500"
    assert page.fields["csrf_token"]["value"]
    assert page.labels == ["amount", "category", "date", "description"]
    assert [item["value"] for item in page.options] == [
        "", "Food", "Transport", "Bills", "Health", "Entertainment",
        "Shopping", "Other",
    ]
    assert [item["value"] for item in page.options if "selected" in item] == [
        "Food",
    ]
    assert all("required" in page.fields[field]
               for field in ("amount", "category", "date"))
    assert "required" not in page.fields["description"]
    assert b"Save changes</button>" in response.data
    assert b'href="/profile">Cancel</a>' in response.data
    assert b"css/expense.css" in response.data
    assert client.head(path).status_code == 200
    assert client.get(path).status_code == 200
    assert client.get("/profile").status_code == 200
    assert snapshot() == before
    assert db.update_expense(expense["id"], expense["user_id"], 12.5,
                             "Food", "2024-02-29")
    assert PageParser(client.get(path), path).description == ""


@pytest.mark.parametrize("identity", [None, True, "1", 0, -1, 2 ** 63, 999999])
@pytest.mark.parametrize("method", ["get", "head", "post"])
def test_authentication_precedes_lookup_and_validation(
        client, expense, identity, method, monkeypatch):
    if identity is not None:
        with client.session_transaction() as session:
            session["user_id"] = identity

    def unexpected(*args, **kwargs):
        pytest.fail("Anonymous request must not look up expenses")

    monkeypatch.setattr(importlib.import_module("app"), "get_expense_by_id",
                        unexpected)
    before = snapshot()
    for path in (edit_path(expense), "/expenses/0/edit", "/expenses/999999/edit"):
        response = getattr(client, method)(path)
        assert response.status_code == 302
        assert response.headers["Location"] == "/login"
    assert snapshot() == before


def test_deleted_account_redirects(client, expense):
    user_id = db.create_user("Deleted", "deleted@example.com", "password123")
    login(client, "deleted@example.com", "password123")
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    before = snapshot()
    for method in (client.get, client.post):
        assert method(edit_path(expense)).headers["Location"] == "/login"
    assert snapshot() == before


@pytest.mark.parametrize("expense_id", [0, 999999, 2 ** 63, 10 ** 100])
@pytest.mark.parametrize("method", ["get", "post"])
def test_unavailable_ids_are_404(client, expense, expense_id, method):
    login(client)
    before = snapshot()
    response = getattr(client, method)("/expenses/{}/edit".format(expense_id))
    assert response.status_code == 404
    assert b"Lunch" not in response.data
    assert snapshot() == before


def test_other_user_expense_is_404_even_with_valid_csrf(client, expense):
    other_id = db.create_user("Other", "other@example.com", "password123")
    own_id = db.create_expense(other_id, 1, "Other", "2024-01-01")
    login(client, "other@example.com", "password123")
    own_path = "/expenses/{}/edit".format(own_id)
    token = PageParser(client.get(own_path), own_path).fields[
        "csrf_token"]["value"]
    before = snapshot()
    assert client.get(edit_path(expense)).status_code == 404
    response = client.post(edit_path(expense), data={"csrf_token": token})
    assert response.status_code == 404
    assert b"Lunch" not in response.data
    assert snapshot() == before


@pytest.mark.parametrize("field,value", [
    ("amount", None), ("amount", ""), ("amount", "0"), ("amount", "-1"),
    ("amount", "+1"), ("amount", "NaN"), ("amount", "inf"),
    ("amount", "1e2"), ("amount", "1.234"), ("amount", "1000000000"),
    ("amount", ".50"), ("amount", "12."), ("amount", "1,000"),
    ("amount", "₹12"), ("amount", "１２"),
    ("category", None), ("category", ""), ("category", "Unknown"),
    ("category", "food"), ("category", " Food "),
    ("date", None), ("date", ""), ("date", "2023-02-29"),
    ("date", "2024-02-30"), ("date", "2024-2-01"),
    ("date", " 2024-02-29 "), ("date", "2024-02-29T12:00:00"),
    ("description", "x" * 501),
])
def test_invalid_fields_do_not_write(client, expense, field, value):
    login(client)
    before = snapshot()
    response = submit(client, expense, **{field: value})
    assert response.status_code == 400
    page = PageParser(response, edit_path(expense))
    assert page.fields[field]["aria-invalid"] == "true"
    assert field + "-error" in page.fields[field]["aria-describedby"]
    assert snapshot() == before


@pytest.mark.parametrize("amount", ["0.01", "12", "12.5", "12.50",
                                    "999999999.99", " 12.50 "])
def test_valid_amounts(client, expense, amount):
    login(client)
    assert submit(client, expense, amount=amount).status_code == 302
    assert Decimal(str(saved(expense)["amount"])) == Decimal(amount.strip())


@pytest.mark.parametrize("category", [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
])
def test_valid_categories(client, expense, category):
    login(client)
    assert submit(client, expense, category=category).status_code == 302
    assert saved(expense)["category"] == category


@pytest.mark.parametrize("expense_date", ["1900-01-01", "2024-02-29",
                                          date.today().isoformat(), "9999-12-31"])
def test_valid_dates(client, expense, expense_date):
    login(client)
    assert submit(client, expense, date=expense_date).status_code == 302
    assert saved(expense)["date"] == expense_date


@pytest.mark.parametrize("description", [None, "", " \n\t ", " x ", "x" * 500])
def test_description_normalization_and_clearing(client, expense, description):
    login(client)
    assert submit(client, expense, description=description).status_code == 302
    assert saved(expense)["description"] == ((description or "").strip() or None)


def test_errors_retain_submitted_escaped_values(client, expense):
    login(client)
    before = snapshot()
    text = '<script>alert("expense")</script>'
    response = submit(client, expense, amount="0", description=text,
                      category="Bills", date="2020-06-01")
    page = PageParser(response, edit_path(expense))
    assert response.status_code == 400
    assert page.fields["amount"]["value"] == "0"
    assert page.fields["date"]["value"] == "2020-06-01"
    assert page.description == text
    assert [item["value"] for item in page.options if "selected" in item] == [
        "Bills",
    ]
    assert b"<script>alert" not in response.data
    response = submit(client, expense, date="bad date", category=text)
    page = PageParser(response, edit_path(expense))
    assert page.fields["date"]["value"] == "bad date"
    assert text not in [item["value"] for item in page.options]
    assert snapshot() == before
    assert submit(client, expense, description=text).status_code == 302
    assert saved(expense)["description"] == text
    assert b"<script>alert" not in client.get(edit_path(expense)).data
    assert b"<script>alert" not in client.get("/profile").data


def test_invalid_csrf_does_not_validate_or_write(client, expense, flask_app,
                                               monkeypatch):
    prelogin = login(client)
    other = flask_app.test_client()
    login(other)
    path = edit_path(expense)
    cross_session = PageParser(other.get(path), path).fields[
        "csrf_token"]["value"]

    def unexpected(*args):
        pytest.fail("Invalid CSRF must be rejected before field validation")

    monkeypatch.setattr(importlib.import_module("app"), "validate_expense_form",
                        unexpected)
    before = snapshot()
    for token in (None, "wrong", cross_session, prelogin):
        response = submit(client, expense, csrf_token=token)
        assert response.status_code == 400
        assert b"Your form has expired. Please try again." in response.data
        assert PageParser(response, path).fields["amount"]["value"] == "15.75"
        assert snapshot() == before


def test_success_preserves_metadata_and_refresh_is_read_only(client, expense):
    login(client)
    before = snapshot()
    path = edit_path(expense)
    token = PageParser(client.get(path), path).fields["csrf_token"]["value"]
    response = client.post(path + "?user_id=999999&id=1&next=https://example.com",
                           data={
                               "amount": "15.75", "category": "Shopping",
                               "date": "2025-01-01", "description": "Updated",
                               "user_id": "999999", "id": "1",
                               "created_at": "forged", "csrf_token": token,
                           })
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    row = saved(expense)
    assert (row["amount"], row["category"], row["date"], row["description"]) == (
        15.75, "Shopping", "2025-01-01", "Updated",
    )
    assert all(row[key] == expense[key] for key in ("id", "user_id", "created_at"))
    after = snapshot()
    assert after["users"] == before["users"]
    assert len(after["expenses"]) == len(before["expenses"])
    assert after["expenses"][:-1] == before["expenses"][:-1]
    profile = client.get("/profile").get_data(as_text=True)
    assert "Expense updated successfully." in profile
    assert 'role="status"' in profile
    assert "Expense updated successfully." not in client.get(
        "/profile").get_data(as_text=True)
    assert snapshot() == after
    assert submit(client, expense).status_code == 302
    assert snapshot() == after
    assert submit(client, expense, amount="20").status_code == 302
    assert saved(expense)["amount"] == 20


def test_helper_ownership_and_unchanged_update(expense):
    before = snapshot()
    assert db.get_expense_by_id(expense["id"], 999999) is None
    assert db.get_expense_by_id(999999, expense["user_id"]) is None
    assert db.get_expense_by_id("1 OR 1=1", expense["user_id"]) is None
    for expense_id, owner in ((expense["id"], 999999), (999999, expense["user_id"]),
                              ("1 OR 1=1", expense["user_id"])):
        assert db.update_expense(expense_id, owner, 1, "Food", "2024-01-01") is False
    assert snapshot() == before
    assert db.update_expense(expense["id"], expense["user_id"], expense["amount"],
                             expense["category"], expense["date"],
                             expense["description"]) is True
    assert snapshot() == before


def test_removed_between_lookup_and_update_is_404(client, expense, monkeypatch):
    login(client)
    module = importlib.import_module("app")
    original_update = db.update_expense

    def removed(expense_id, user_id, **values):
        with closing(db.get_db()) as connection:
            with connection:
                connection.execute("DELETE FROM expenses WHERE id = ?",
                                   (expense_id,))
        return original_update(expense_id, user_id, **values)

    monkeypatch.setattr(module, "update_expense", removed)
    assert submit(client, expense).status_code == 404
    with client.session_transaction() as session:
        assert "_flashes" not in session


def test_ownership_changed_between_lookup_and_update_is_404(
        client, expense, monkeypatch):
    new_owner = db.create_user("Other", "other@example.com", "password123")
    login(client)
    module = importlib.import_module("app")
    original_update = db.update_expense

    def transferred(expense_id, user_id, **values):
        with closing(db.get_db()) as connection:
            with connection:
                connection.execute(
                    "UPDATE expenses SET user_id = ? WHERE id = ?",
                    (new_owner, expense_id),
                )
        return original_update(expense_id, user_id, **values)

    monkeypatch.setattr(module, "update_expense", transferred)
    response = submit(client, expense)
    assert response.status_code == 404
    moved = dict(db.get_expense_by_id(expense["id"], new_owner))
    assert all(moved[field] == expense[field] for field in (
        "id", "amount", "category", "date", "description", "created_at",
    ))
    assert db.get_expense_by_id(expense["id"], expense["user_id"]) is None
    with client.session_transaction() as session:
        assert "_flashes" not in session


def test_helper_commit_rollback_and_connection_closure(expense, monkeypatch):
    original_get_db = db.get_db
    opened = []

    def tracked_connection():
        connection = original_get_db()
        opened.append(connection)
        return connection

    monkeypatch.setattr(db, "get_db", tracked_connection)
    db.get_expense_by_id(expense["id"], expense["user_id"])
    assert db.update_expense(expense["id"], expense["user_id"], 20,
                             "Bills", "2024-01-01")
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    assert saved(expense)["amount"] == 20
    before = snapshot()
    with pytest.raises(sqlite3.IntegrityError):
        db.update_expense(expense["id"], expense["user_id"], None,
                          "Bills", "2024-01-01")
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
        db.update_expense(expense["id"], expense["user_id"], 100,
                          "Other", "2025-01-01")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")
    monkeypatch.setattr(db, "get_db", original_get_db)
    assert snapshot() == before


@pytest.mark.parametrize("helper", ["get_expense_by_id", "update_expense"])
def test_route_database_failures_propagate(client, expense, monkeypatch, helper):
    login(client)
    path = edit_path(expense)
    token = PageParser(client.get(path), path).fields["csrf_token"]["value"]
    before = snapshot()

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("storage unavailable")

    monkeypatch.setattr(importlib.import_module("app"), helper, unavailable)
    with pytest.raises(sqlite3.OperationalError, match="storage unavailable"):
        client.post(path, data={
            "amount": "1", "category": "Food", "date": "2024-01-01",
            "csrf_token": token,
        })
    with client.session_transaction() as session:
        assert "_flashes" not in session
    assert snapshot() == before


def test_profile_links_and_updated_spending(client, flask_app):
    owner = db.create_user("Other", "other@example.com", "password123")
    ids = [db.create_expense(owner, 1, "Food", "2024-05-01",
                             "Purchase {:02d}".format(index))
           for index in range(11)]
    login(client, "other@example.com", "password123")
    expense = dict(db.get_expense_by_id(ids[0], owner))
    assert submit(client, expense, amount="5", category="Bills",
                  date="2024-06-01", description="Moved").status_code == 302
    assert queries.get_summary_stats(owner) == {
        "total_spent": Decimal("15.00"), "transaction_count": 11,
        "top_category": "Food",
    }
    assert queries.get_category_breakdown(owner) == [
        {"name": "Food", "amount": Decimal("10.00"), "pct": 67},
        {"name": "Bills", "amount": Decimal("5.00"), "pct": 33},
    ]
    for path, expected_ids in (
        ("/profile", [ids[0]] + ids[:1:-1]),
        ("/profile?start_date=2024-05-01&end_date=2024-05-01", ids[:0:-1]),
        ("/profile?start_date=2024-06-01&end_date=2024-06-01", [ids[0]]),
    ):
        response = client.get(path)
        links = [link for link in PageParser(response).links
                 if link.get("class") == "profile-edit"]
        assert [link["href"] for link in links] == [
            "/expenses/{}/edit".format(expense_id) for expense_id in expected_ids
        ]
        assert [link["aria-label"] for link in links] == [
            "Edit expense #{}".format(expense_id) for expense_id in expected_ids
        ]
    assert submit(client, expense, amount="5", date="2020-01-01",
                  category="Bills", description="Older").status_code == 302
    assert b"Older" not in client.get("/profile").data
    assert queries.get_summary_stats(owner)["total_spent"] == Decimal("15.00")
    assert b'colspan="5"' in client.get(
        "/profile?start_date=2025-01-01").data
    demo = flask_app.test_client()
    login(demo)
    response = demo.get("/profile")
    assert "₹235.50" in response.get_data(as_text=True)
    assert b"Older" not in response.data
    assert demo.get(edit_path(expense)).status_code == 404
