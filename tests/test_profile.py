"""Profile access and rendering against isolated account data."""

import importlib
import re
from contextlib import closing
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest

from database import db


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "profile.db")
    monkeypatch.setenv("SECRET_KEY", "profile-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    application = importlib.import_module("app").app
    db.init_db()
    db.seed_db()
    for key, value in {
        "TESTING": True, "SECRET_KEY": "profile-test-secret",
        "SESSION_COOKIE_SECURE": False,
    }.items():
        monkeypatch.setitem(application.config, key, value)
    return application


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


class PageParser(HTMLParser):
    def __init__(self, response, section_id=None, section_class=None):
        super().__init__()
        self.elements = []
        self.nodes = []
        self.stack = []
        self.section_id = section_id
        self.section_class = section_class
        self.feed(response.get_data(as_text=True))

    def matches_section(self, attributes):
        return (
            self.section_id is not None
            and attributes.get("id") == self.section_id
        ) or (
            self.section_class is not None
            and self.section_class in attributes.get("class", "").split()
        )

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        node = {"tag": tag, "attrs": attributes, "text": ""}
        within_section = any(
            self.matches_section(parent["attrs"])
            for parent in self.stack
        )
        if ((self.section_id is None and self.section_class is None)
                or self.matches_section(attributes) or within_section):
            self.elements.append((tag, attributes))
            self.nodes.append(node)
        if tag not in ("meta", "link", "input", "img", "br", "hr"):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data

    def texts(self, tag):
        return [node["text"].strip() for node in self.nodes
                if node["tag"] == tag]

    def attributes(self, tag):
        return [attrs for element, attrs in self.elements if element == tag]

    def profile_link(self):
        return next(attrs for attrs in self.attributes("a")
                    if attrs.get("href") == "/profile")

    def csrf_token(self):
        return next(attrs["value"] for attrs in self.attributes("input")
                    if attrs.get("name") == "csrf_token")


def login(client, email="demo@spendly.com", password="demo123"):
    token = PageParser(client.get("/login")).csrf_token()
    response = client.post("/login", data={
        "email": email, "password": password, "csrf_token": token,
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"


def snapshot():
    with closing(db.get_db()) as connection:
        return (
            [tuple(row) for row in connection.execute(
                "SELECT * FROM users ORDER BY id")],
            [tuple(row) for row in connection.execute(
                "SELECT * FROM expenses ORDER BY id")],
        )


def test_anonymous_access_and_methods(client, monkeypatch):
    from database import queries

    def unexpected_lookup(*args):
        pytest.fail("Anonymous requests must not query profile data")

    for name in ("get_user_by_id", "get_summary_stats",
                 "get_recent_transactions", "get_category_breakdown"):
        monkeypatch.setattr(queries, name, unexpected_lookup)
    baseline = snapshot()
    for method in ("get", "head"):
        response = getattr(client, method)("/profile")
        assert response.status_code == 302
        assert response.headers["Location"] == "/login"
        assert b"demo@spendly.com" not in response.data
    assert b"Sign in to your Spendly account" in client.get(
        "/profile", follow_redirects=True,
    ).data
    assert client.post("/profile").status_code == 405
    assert snapshot() == baseline


def test_demo_profile_semantics_and_read_only_requests(client):
    login(client)
    baseline = snapshot()
    response = client.get("/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    page = PageParser(response)
    assert "Profile — Spendly" in html
    assert "Demo User" in html
    assert "aarav.sharma@example.com" not in html
    assert "demo@spendly.com" in html
    assert "coming in Step 4" not in html
    assert len(page.attributes("h1")) == 1
    account = PageParser(response, "profile-account-fields")
    assert len(account.attributes("dl")) == 1
    assert len(account.attributes("dt")) == 3
    assert len(account.attributes("dd")) == 3
    for label in ("Full name", "Email address", "Member since"):
        assert "<dt>{}</dt>".format(label) in html
    initial = next(attrs for attrs in page.attributes("span")
                   if attrs.get("class") == "profile-initial")
    assert initial["aria-hidden"] == "true"
    assert page.profile_link()["aria-current"] == "page"
    assert page.profile_link()["aria-label"] == "View profile for Demo User"
    user = db.get_user_by_email("demo@spendly.com")
    assert user["password_hash"] not in html
    assert account.attributes("time") == [{
        "id": "profile-member-since", "datetime": user["created_at"][:10],
    }]
    logout_page = PageParser(response, section_class="nav-logout")
    assert logout_page.attributes("form") == [{
        "class": "nav-logout", "method": "POST", "action": "/logout",
    }]
    assert [attrs["name"] for attrs in logout_page.attributes("input")] == [
        "csrf_token",
    ]
    assert logout_page.csrf_token()
    assert len(page.attributes("form")) == 2
    stylesheet = next(attrs["href"] for attrs in page.attributes("link")
                      if attrs.get("href", "").endswith("css/profile.css"))
    assert client.get(stylesheet).status_code == 200
    head = client.head("/profile")
    assert head.status_code == 200 and head.data == b""
    assert client.post("/profile").status_code == 405
    assert snapshot() == baseline


def test_two_accounts_keep_private_data_and_ignore_requested_id(client, flask_app):
    other = flask_app.test_client()
    response = other.post("/register", data={
        "name": "Other Person", "email": "other@example.com",
        "password": "other-password", "confirm_password": "other-password",
    })
    assert response.status_code == 302
    login(client)
    login(other, "other@example.com", "other-password")
    demo_id = db.get_user_by_email("demo@spendly.com")["id"]
    other_id = db.get_user_by_email("other@example.com")["id"]
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                (other_id, 1234, "Shopping", "2020-01-01", "Private purchase"),
            )
    for browser, requested_id, own_name, foreign_name in (
        (client, other_id, "Demo User", "Other Person"),
        (other, demo_id, "Other Person", "Demo User"),
    ):
        response = browser.get("/profile?user_id={}".format(requested_id))
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert own_name in html
        assert foreign_name not in html
        assert "Aarav Sharma" not in html
        if browser is other:
            assert "Private purchase" in html and "₹1,234.00" in html
            assert "₹235.50" not in html
        else:
            assert "Private purchase" not in html and "₹235.50" in html
        link = PageParser(response).profile_link()
        assert link["aria-label"] == "View profile for " + own_name
        assert foreign_name not in link["aria-label"]


@pytest.mark.parametrize("user_id", [
    None, True, "1", 1.0, [], {}, 0, -1, 2 ** 63, 999999,
])
def test_invalid_identity_redirects_and_clears_session(client, user_id):
    with client.session_transaction() as current:
        current.update(user_id=user_id, csrf_token="stale")
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as current:
        assert dict(current) == {}


def test_deleted_account_and_tampered_cookie(client):
    user_id = db.create_user("Temporary", "temporary@example.com", "secret123")
    login(client, "temporary@example.com", "secret123")
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    assert client.get("/profile").headers["Location"] == "/login"
    login(client)
    cookie = client.get_cookie("session").value
    payload, signature = cookie.rsplit(".", 1)
    changed = ("A" if signature[0] != "A" else "B") + signature[1:]
    client.set_cookie("session", payload + "." + changed)
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert b"demo@spendly.com" not in response.data


@pytest.mark.parametrize("stored", [None, "", "invalid", "2024-02-29 12:34:56"])
def test_membership_date_uses_stored_account_date_or_fallback(client, stored):
    login(client)
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "UPDATE users SET created_at = ? WHERE email = ?",
                (stored, "demo@spendly.com"),
            )
    response = client.get("/profile")
    assert response.status_code == 200
    account = PageParser(response, "profile-account-fields")
    if stored == "2024-02-29 12:34:56":
        assert account.texts("dd")[-1] == "February 2024"
        assert account.attributes("time") == [{
            "id": "profile-member-since", "datetime": "2024-02-29",
        }]
    else:
        assert account.texts("dd")[-1] == "—"
        assert account.attributes("time") == []


def test_user_text_is_escaped_in_content_and_attributes(client):
    login(client)
    name = '<script>alert("name")</script>'
    email = '\"><img src=x onerror=alert(1)>@example.com'
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "UPDATE users SET name = ?, email = ? WHERE email = ?",
                (name, email, "demo@spendly.com"),
            )
    response = client.get("/profile")
    html = response.get_data(as_text=True)
    page = PageParser(response)
    assert name not in html and email not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html
    assert page.attributes("img") == []
    assert page.profile_link()["aria-label"] == "View profile for " + name
    assert page.profile_link()["title"] == name
    assert db.get_user_by_email(email)["password_hash"] not in html


@pytest.mark.parametrize("name,accessible_name,initials", [
    ("", "Your profile", "?"),
    (" \t ", "Your profile", "?"),
    ("  Élodie", "View profile for   Élodie", "É"),
    ("Alex Middle Smith", "View profile for Alex Middle Smith", "AS"),
])
def test_initial_and_real_name_navigation(client, name, accessible_name, initials):
    login(client)
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "UPDATE users SET name = ? WHERE email = ?",
                (name, "demo@spendly.com"),
            )
    response = client.get("/profile")
    assert 'class="profile-initial" aria-hidden="true">{}</span>'.format(initials) in (
        response.get_data(as_text=True)
    )
    link = PageParser(response).profile_link()
    assert link["aria-label"] == accessible_name


def test_navigation_and_logout(client):
    paths = ("/", "/register", "/terms", "/privacy")
    for path in paths + ("/login",):
        response = client.get(path)
        assert response.status_code == 200
        assert b"Get started" in response.data
        assert b'href="/profile"' not in response.data
    login(client)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert "aria-current" not in PageParser(response).profile_link()
        assert b"css/profile.css" not in response.data
    page = PageParser(client.get("/profile"))
    baseline = snapshot()
    response = client.post("/logout", data={"csrf_token": page.csrf_token()})
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert client.get("/profile").headers["Location"] == "/login"
    assert snapshot() == baseline


def test_dashboard_sections_and_reconciled_seed_totals(client):
    login(client)
    baseline = snapshot()
    response = client.get("/profile")
    assert response.status_code == 200
    assert "All-time spending" in response.get_data(as_text=True)
    assert "Sample data" not in response.get_data(as_text=True)

    summary = PageParser(response, "profile-summary")
    stats = dict(zip(summary.texts("dt"), summary.texts("dd")))
    assert stats == {
        "Total spent": "₹235.50", "Transactions": "8",
        "Top category": "Bills",
    }

    table = PageParser(response, "profile-transactions")
    assert table.texts("th") == ["Date", "Description", "Category", "Amount"]
    assert all(attrs["scope"] == "col" for attrs in table.attributes("th"))
    assert table.texts("caption") == [
        "Your most recent expenses (INR)",
    ]
    cells = table.texts("td")
    rows = [cells[index:index + 4] for index in range(0, len(cells), 4)]
    assert len(rows) == 8
    assert rows[0][1:] == ["—", "Food", "₹25.00"]
    assert rows[-1][1:] == ["—", "Food", "₹12.50"]
    dates = [datetime.strptime(row[0], "%d %b %Y") for row in rows]
    assert dates == sorted(dates, reverse=True)
    assert len(table.attributes("time")) == len(rows)

    def money(value):
        return Decimal(value.lstrip("₹").replace(",", ""))

    category_sums = {}
    for _, _, category, amount in rows:
        previous = category_sums.get(category, Decimal(0))
        category_sums[category] = previous + money(amount)
    breakdown = PageParser(response, "profile-categories")
    assert len(breakdown.attributes("li")) == 7
    displayed = {}
    percentages = []
    for entry in breakdown.texts("li"):
        category, _, amount = entry.partition("₹")
        amount, _, percentage = amount.partition("(")
        displayed[category.strip()] = Decimal(amount.strip().replace(",", ""))
        percentages.append(int(percentage.rstrip("%)")))
    assert displayed == category_sums
    assert sum(displayed.values()) == money(stats["Total spent"])
    assert int(stats["Transactions"]) == len(rows)
    assert max(displayed, key=displayed.get) == stats["Top category"]
    assert sum(percentages) == 100
    assert snapshot() == baseline


def test_profile_reflects_persisted_expenses_without_writes(client):
    login(client)
    before = client.get("/profile")
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("UPDATE expenses SET amount = ?", (999999,))
    baseline = snapshot()
    after = client.get("/profile")
    for section_id in (
        "profile-summary", "profile-transactions", "profile-categories",
    ):
        expected = PageParser(before, section_id).nodes
        assert PageParser(after, section_id).nodes != expected
    assert PageParser(after, "profile-account-fields").nodes == PageParser(
        before, "profile-account-fields",
    ).nodes
    assert "999,999" in after.get_data(as_text=True)
    assert snapshot() == baseline


def test_dashboard_styles_use_classes_and_table_is_keyboard_accessible(client):
    login(client)
    response = client.get("/profile")
    page = PageParser(response)
    scroll_region = next(attrs for attrs in page.attributes("div")
                         if attrs.get("class") == "profile-table-scroll")
    assert scroll_region["tabindex"] == "0"
    assert scroll_region["role"] == "region"
    assert scroll_region["aria-labelledby"] == "transactions-title"
    assert all("style" not in attrs for _, attrs in page.elements)
    badges = [attrs for attrs in page.attributes("span")
              if "profile-category" in attrs.get("class", "").split()]
    assert len(badges) == 15
    for attrs in badges:
        assert any("profile-category-" + category in attrs["class"].split()
                   for category in ("bills", "food", "transport", "health",
                                    "entertainment", "shopping", "other"))
    project = Path(__file__).resolve().parents[1]
    for path in ("templates/profile.html", "static/css/profile.css"):
        source = (project / path).read_text()
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", source)


def test_profile_icons_are_decorative_and_lucide_loads_once(client):
    login(client)
    response = client.get("/profile")
    page = PageParser(response)
    icon_names = [attrs["data-lucide"] for attrs in page.attributes("i")]
    assert icon_names == ["wallet", "receipt", "tag", "credit-card", "tags"]
    icon_wrappers = [
        attrs for attrs in page.attributes("span")
        if attrs.get("class") == "profile-icon"
    ]
    assert len(icon_wrappers) == len(icon_names)
    assert all(attrs.get("aria-hidden") == "true" for attrs in icon_wrappers)
    scripts = [attrs.get("src", "") for attrs in page.attributes("script")]
    lucide = [src for src in scripts if "unpkg.com/lucide@0.510.0" in src]
    assert lucide == [
        "https://unpkg.com/lucide@0.510.0/dist/umd/lucide.min.js",
    ]
    public = PageParser(client.get("/"))
    public_scripts = [attrs.get("src", "") for attrs in public.attributes("script")]
    assert not any("unpkg.com/lucide" in src for src in public_scripts)
    main_js = client.get("/static/js/main.js").get_data(as_text=True)
    assert "document.querySelector(\"[data-lucide]\")" in main_js
    assert "window.lucide" in main_js


def test_new_account_empty_profile(client):
    response = client.post("/register", data={
        "name": "New Person", "email": "new@example.com",
        "password": "password123", "confirm_password": "password123",
    })
    assert response.status_code == 302
    login(client, "new@example.com", "password123")
    response = client.get("/profile")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "New Person" in html and "new@example.com" in html
    assert "Demo User" not in html and "Sample data" not in html
    assert PageParser(response, "profile-summary").texts("dd") == ["₹0.00", "0", "—"]
    assert "No expenses recorded yet." in html
    assert "No category spending yet." in html


def test_expense_content_is_escaped_with_safe_category_class(client):
    login(client)
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "UPDATE expenses SET category = ?, description = ?",
                ('\"><img src=x onerror=alert(1)>', '<script>alert(1)</script>'),
            )
    response = client.get("/profile")
    html = response.get_data(as_text=True)
    assert "&lt;img" in html and "&lt;script&gt;" in html
    assert PageParser(response).attributes("img") == []
    assert all("profile-category-other" in attrs["class"].split()
               for attrs in PageParser(response).attributes("span")
               if "profile-category" in attrs.get("class", "").split())


@pytest.mark.parametrize("bounds", [
    {}, {"start_date": "2020-01-01", "end_date": "2020-01-01"},
])
def test_route_history_limit_does_not_limit_summary(client, bounds):
    login(client)
    user_id = db.get_user_by_email("demo@spendly.com")["id"]
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
            connection.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                [(user_id, 10, "Food", "2020-01-01", "Expense {}".format(n))
                 for n in range(12)],
            )
    response = client.get("/profile", query_string=bounds)
    assert PageParser(response, "profile-summary").texts("dd") == ["₹120.00", "12", "Food"]
    assert len(PageParser(response, "profile-transactions").texts("td")) == 40
    assert PageParser(response, "profile-transactions").texts("td")[1::4] == [
        "Expense {}".format(n) for n in range(11, 1, -1)
    ]
    hint = "at most ten matching expenses" if bounds else "at most ten expenses"
    assert hint in response.get_data(as_text=True)
    assert "₹120.00" in PageParser(response, "profile-categories").texts("li")[0]
    assert "(100%)" in PageParser(response, "profile-categories").texts("li")[0]


@pytest.mark.parametrize("query_string", [{}, {"start_date": "2026-01-01"}])
@pytest.mark.parametrize("helper", [
    "get_summary_stats", "get_recent_transactions", "get_category_breakdown",
])
def test_profile_does_not_mask_database_failure(
    client, monkeypatch, query_string, helper,
):
    import sqlite3
    from database import queries

    login(client)

    def unavailable(user_id, start_date=None, end_date=None):
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(queries, helper, unavailable)
    with pytest.raises(sqlite3.OperationalError, match="database unavailable"):
        client.get("/profile", query_string=query_string)


@pytest.fixture
def dated_expenses(client):
    login(client)
    user_id = db.get_user_by_email("demo@spendly.com")["id"]
    rows = [
        (1, "Other", "2024-02-28", "Before"),
        (2, "Food", "2024-02-29", "Start"),
        (3, "Food", "2024-03-01", "Middle"),
        (4, "Bills", "2024-03-02", "End"),
        (5, "Other", "2099-01-01", "Future"),
    ]
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
            connection.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                [(user_id,) + row for row in rows],
            )
    return user_id


@pytest.mark.parametrize("bounds,expected,total,top", [
    ({}, ["Future", "End", "Middle", "Start", "Before"], "15.00", "Other"),
    ({"start_date": "", "end_date": ""},
     ["Future", "End", "Middle", "Start", "Before"], "15.00", "Other"),
    ({"start_date": "2024-02-29", "end_date": "2024-03-02"},
     ["End", "Middle", "Start"], "9.00", "Food"),
    ({"start_date": "2024-02-29", "end_date": "2024-02-29"},
     ["Start"], "2.00", "Food"),
    ({"start_date": "2024-03-02"}, ["Future", "End"], "9.00", "Other"),
    ({"end_date": "2024-02-29"}, ["Start", "Before"], "3.00", "Food"),
    ({"start_date": "", "end_date": "2024-02-29"},
     ["Start", "Before"], "3.00", "Food"),
    ({"start_date": "2099-01-01", "end_date": ""}, ["Future"], "5.00", "Other"),
])
def test_profile_date_ranges(client, dated_expenses, bounds, expected, total, top):
    baseline = snapshot()
    account = PageParser(client.get("/profile"), "profile-account-fields").nodes
    response = client.get("/profile", query_string=bounds)
    assert response.status_code == 200
    assert PageParser(response, "profile-summary").texts("dd") == [
        "₹" + total, str(len(expected)), top,
    ]
    assert PageParser(response, "profile-transactions").texts("td")[1::4] == expected
    assert PageParser(response, "profile-account-fields").nodes == account
    inputs = PageParser(response, "profile-filter").attributes("input")
    assert {item["name"]: item["value"] for item in inputs} == {
        name: bounds.get(name, "") for name in ("start_date", "end_date")
    }
    categories = PageParser(response, "profile-categories").texts("li")
    assert sum(Decimal(re.search(r"₹([\d.]+)", row).group(1))
               for row in categories) == Decimal(total)
    assert sum(int(re.search(r"\((\d+)%\)", row).group(1))
               for row in categories) == 100
    range_text = PageParser(response, "profile-active-range").texts("p")[0]
    for value in bounds.values():
        if value:
            assert value in range_text
    assert client.get(response.request.url).data == response.data
    assert snapshot() == baseline


def test_valid_bounds_reach_all_spending_helpers_unchanged(
    client, dated_expenses, monkeypatch,
):
    from database import queries

    observed = {}
    originals = {
        name: getattr(queries, name)
        for name in ("get_summary_stats", "get_recent_transactions",
                     "get_category_breakdown")
    }

    def recording_helper(name):
        def call(user_id, *args, **kwargs):
            observed[name] = (user_id, args, kwargs)
            return originals[name](user_id, *args, **kwargs)
        return call

    for name in originals:
        monkeypatch.setattr(queries, name, recording_helper(name))
    response = client.get("/profile?start_date=2024-02-29&end_date=2024-03-02")
    assert response.status_code == 200
    assert observed == {
        name: (dated_expenses, (), {
            "start_date": "2024-02-29", "end_date": "2024-03-02",
        }) for name in originals
    }


@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize("invalid", [
    "garbage", "2026-2-01", "2026-02-1", "2026-02-29", "2024-02-30",
    "2026-13-01", "0000-01-01", "2026-01-01T00:00:00",
    " 2026-01-01", "2026-01-01 ", "2026-01-01\n", "２０２６-01-01",
    '\"><img src=x onerror=alert(1)>', "2026-01-01' OR 1=1 --",
])
def test_invalid_dates_skip_spending_queries(client, monkeypatch, field, invalid):
    from database import queries

    login(client)
    baseline = snapshot()

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid filters must not query spending")

    for helper in ("get_summary_stats", "get_recent_transactions",
                   "get_category_breakdown"):
        monkeypatch.setattr(queries, helper, unexpected)
    other = "end_date" if field == "start_date" else "start_date"
    response = client.get("/profile", query_string={field: invalid, other: "2026-01-01"})
    assert response.status_code == 400
    page = PageParser(response)
    assert page.attributes("img") == []
    assert PageParser(response, "profile-account-fields").texts("dd")[0] == "Demo User"
    for section in ("profile-summary", "profile-transactions", "profile-categories"):
        assert PageParser(response, section).nodes == []
    inputs = {item["name"]: item for item in
              PageParser(response, "profile-filter").attributes("input")}
    assert inputs[field]["value"] == ""
    assert inputs[other]["value"] == "2026-01-01"
    assert inputs[field]["aria-invalid"] == "true"
    error_id = inputs[field]["aria-describedby"]
    assert "YYYY-MM-DD" in PageParser(response, error_id).texts("p")[0]
    assert any(attrs.get("role") == "alert" for attrs in page.attributes("p"))
    assert snapshot() == baseline


def test_reversed_range_retains_dates_and_skips_queries(client, monkeypatch):
    from database import queries

    login(client)

    def unexpected(*args, **kwargs):
        pytest.fail("Reversed ranges must not query spending")

    for helper in ("get_summary_stats", "get_recent_transactions",
                   "get_category_breakdown"):
        monkeypatch.setattr(queries, helper, unexpected)
    response = client.get("/profile?start_date=2026-02-01&end_date=2026-01-01")
    assert response.status_code == 400
    assert [item["value"] for item in PageParser(
        response, "profile-filter",
    ).attributes("input")] == ["2026-02-01", "2026-01-01"]
    assert b"End date must be on or after start date." in response.data
    assert PageParser(response, "profile-summary").nodes == []


def test_filter_form_empty_range_clear_and_logout(client, dated_expenses):
    baseline = snapshot()
    response = client.get("/profile?start_date=2050-01-01&end_date=2050-12-31")
    assert response.status_code == 200
    assert PageParser(response, "profile-summary").texts("dd") == ["₹0.00", "0", "—"]
    assert PageParser(response, "profile-transactions").texts("td") == [
        "No expenses in this date range.",
    ]
    assert PageParser(response, "profile-categories").texts("li") == [
        "No category spending in this date range.",
    ]
    form = PageParser(response, "profile-filter")
    assert form.attributes("form")[0]["method"] == "GET"
    assert form.attributes("form")[0]["action"] == "/profile"
    assert form.attributes("input") and all(
        item["name"] != "csrf_token" for item in form.attributes("input")
    )
    assert form.texts("label") == ["Start date", "End date"]
    assert [attrs["for"] for attrs in form.attributes("label")] == [
        "start_date", "end_date",
    ]
    assert all(item["type"] == "date" and item["id"] == item["name"]
               and "required" not in item for item in form.attributes("input"))
    assert len(form.attributes("input")) == 2
    assert any(button.get("type") == "submit" and label == "Apply filter"
               for button, label in zip(form.attributes("button"), form.texts("button")))
    assert any(label == "Clear filter" and attrs.get("href") == "/profile"
               for attrs, label in zip(form.attributes("a"), form.texts("a")))
    clear = form.attributes("a")[0]["href"]
    assert clear == "/profile"
    assert PageParser(client.get(clear), "profile-summary").texts("dd")[0] == "₹15.00"
    with client.session_transaction() as current:
        assert "start_date" not in current and "end_date" not in current
    assert client.post("/logout").status_code == 400
    token = PageParser(response).csrf_token()
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert snapshot() == baseline


@pytest.mark.parametrize("identity", [None, "invalid", 999999])
def test_authentication_precedes_invalid_filter(client, identity):
    if identity is not None:
        with client.session_transaction() as current:
            current["user_id"] = identity
    response = client.get("/profile?start_date=invalid")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_filtered_results_ignore_other_user_id(client, flask_app, dated_expenses):
    other_id = db.create_user("Other", "filtered-other@example.com", "secret123")
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (other_id, 999, "Other", "2024-02-29", "Private expense"),
            )
    response = client.get("/profile", query_string={
        "start_date": "2024-02-29", "end_date": "2024-02-29", "user_id": other_id,
    })
    assert PageParser(response, "profile-summary").texts("dd") == ["₹2.00", "1", "Food"]
    assert b"Private expense" not in response.data
    other_client = flask_app.test_client()
    login(other_client, "filtered-other@example.com", "secret123")
    response = other_client.get("/profile", query_string={
        "start_date": "2024-02-29", "end_date": "2024-02-29", "user_id": dated_expenses,
    })
    assert PageParser(response, "profile-summary").texts("dd") == ["₹999.00", "1", "Other"]


@pytest.mark.parametrize("today,expected", [
    (date(2026, 10, 4), [
        ("Last Month", "2026-09-01", "2026-09-30"),
        ("Last 3 Months", "2026-07-01", "2026-09-30"),
        ("Last 6 Months", "2026-04-01", "2026-09-30"),
    ]),
    (date(2026, 1, 15), [
        ("Last Month", "2025-12-01", "2025-12-31"),
        ("Last 3 Months", "2025-10-01", "2025-12-31"),
        ("Last 6 Months", "2025-07-01", "2025-12-31"),
    ]),
    (date(2024, 3, 1), [
        ("Last Month", "2024-02-01", "2024-02-29"),
        ("Last 3 Months", "2023-12-01", "2024-02-29"),
        ("Last 6 Months", "2023-09-01", "2024-02-29"),
    ]),
])
def test_presets_cover_previous_complete_months(flask_app, today, expected):
    from app import profile_date_presets

    assert [
        (item["label"], item["start_date"], item["end_date"])
        for item in profile_date_presets(today)
    ] == expected


def test_preset_links_filter_dashboard_and_clear_without_writes(
    client, monkeypatch,
):
    import app as application

    login(client)
    user_id = db.get_user_by_email("demo@spendly.com")["id"]
    rows = [
        (20, "Other", "2026-03-31", "Before six months"),
        (1, "Food", "2026-04-01", "Six month start"),
        (2, "Food", "2026-06-30", "Before three months"),
        (3, "Bills", "2026-07-01", "Three month start"),
        (4, "Bills", "2026-08-31", "Before last month"),
        (5, "Shopping", "2026-09-01", "Last month start"),
        (6, "Shopping", "2026-09-30", "Last month end"),
        (30, "Other", "2026-10-01", "Current month"),
    ]
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
            connection.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                [(user_id,) + row for row in rows],
            )
    expected_ranges = [
        ("Last Month", "2026-09-01", "2026-09-30", "₹11.00", "2",
         ["Last month end", "Last month start"]),
        ("Last 3 Months", "2026-07-01", "2026-09-30", "₹18.00", "4",
         ["Last month end", "Last month start", "Before last month",
          "Three month start"]),
        ("Last 6 Months", "2026-04-01", "2026-09-30", "₹21.00", "6",
         ["Last month end", "Last month start", "Before last month",
          "Three month start", "Before three months", "Six month start"]),
    ]
    monkeypatch.setattr(application, "profile_date_presets", lambda: [
        {"label": label, "start_date": start, "end_date": end}
        for label, start, end, _, _, _ in expected_ranges
    ])
    baseline = snapshot()
    initial = client.get("/profile")
    assert initial.status_code == 200
    links = PageParser(initial, "profile-filter").attributes("a")
    assert PageParser(initial, "profile-filter").texts("a") == [
        "Clear filter", "Last Month", "Last 3 Months", "Last 6 Months",
    ]
    assert all(link.get("aria-current") is None for link in links)
    assert PageParser(initial, "profile-summary").texts("dd") == [
        "₹71.00", "8", "Other",
    ]
    account = PageParser(initial, "profile-account-fields").nodes
    for index, (_, start, end, total, count, descriptions) in enumerate(
        expected_ranges, start=1,
    ):
        assert links[index]["href"] == (
            "/profile?start_date={}&end_date={}".format(start, end)
        )
        response = client.get(links[index]["href"])
        assert response.status_code == 200
        form = PageParser(response, "profile-filter")
        assert [item["value"] for item in form.attributes("input")] == [start, end]
        assert [item.get("aria-current") for item in form.attributes("a")] == [
            "true" if position == index else None for position in range(4)
        ]
        assert PageParser(response, "profile-summary").texts("dd") == [
            total, count, "Shopping",
        ]
        assert PageParser(response, "profile-account-fields").nodes == account
        assert PageParser(response, "profile-transactions").texts("td")[1::4] == (
            descriptions
        )
        assert sum(Decimal(re.search(r"₹([\d.]+)", row).group(1)) for row in
                   PageParser(response, "profile-categories").texts("li")) == (
            Decimal(total.lstrip("₹"))
        )
    for path in (
        "/profile?start_date=2026-09-02&end_date=2026-09-30",
        "/profile?start_date=invalid",
    ):
        assert all(link.get("aria-current") is None for link in PageParser(
            client.get(path), "profile-filter",
        ).attributes("a"))
    cleared = client.get(links[0]["href"])
    assert cleared.request.query_string == b""
    assert PageParser(cleared, "profile-summary").texts("dd") == [
        "₹71.00", "8", "Other",
    ]
    assert all(link.get("aria-current") is None for link in PageParser(
        cleared, "profile-filter",
    ).attributes("a"))
    assert snapshot() == baseline
