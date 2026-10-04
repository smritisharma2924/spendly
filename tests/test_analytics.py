"""Analytics access and navigation using an isolated database."""

import importlib
from html.parser import HTMLParser

import pytest

from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "analytics.db")
    monkeypatch.setenv("SECRET_KEY", "analytics-test-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    application = importlib.import_module("app").app
    db.init_db()
    db.seed_db()
    for key, value in {
        "TESTING": True, "SECRET_KEY": "analytics-test-secret",
        "SESSION_COOKIE_SECURE": False,
    }.items():
        monkeypatch.setitem(application.config, key, value)
    return application.test_client()


class Page(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.links = []
        self.token = None
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs)
        if tag == "input" and attrs.get("name") == "csrf_token":
            self.token = attrs["value"]


def login(client):
    token = Page(client.get("/login")).token
    response = client.post("/login", data={
        "email": "demo@spendly.com", "password": "demo123",
        "csrf_token": token,
    })
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"


@pytest.mark.parametrize("method", ["get", "head"])
def test_anonymous_analytics_redirects_to_login(client, method):
    response = getattr(client, method)("/analytics")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


@pytest.mark.parametrize("user_id", [999999, "1", True, -1])
def test_invalid_or_stale_session_cannot_access_analytics(client, user_id):
    with client.session_transaction() as session:
        session["user_id"] = user_id
    response = client.get("/analytics")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as session:
        assert "user_id" not in session


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/terms", "/privacy"])
def test_anonymous_navbar_has_no_analytics_link(client, path):
    assert not any(link.get("href") == "/analytics"
                   for link in Page(client.get(path)).links)


def test_logged_in_analytics_renders_and_marks_only_analytics_active(client):
    login(client)
    response = client.get("/analytics")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Advanced Analytics" in html
    assert "Coming soon" in html
    assert 'aria-valuenow="72"' in html
    active_links = [link["href"] for link in Page(response).links
                    if link.get("aria-current") == "page"]
    assert active_links == ["/analytics"]


@pytest.mark.parametrize("path", ["/", "/profile", "/terms", "/privacy"])
def test_analytics_nav_link_visible_but_inactive_on_other_pages(client, path):
    login(client)
    links = [link for link in Page(client.get(path)).links
             if link.get("href") == "/analytics"]
    assert len(links) == 1
    assert "aria-current" not in links[0]


def test_analytics_policy_links_and_logout(client):
    login(client)
    page = Page(client.get("/analytics"))
    destinations = {link.get("href") for link in page.links}
    for path, title in [("/terms", "Terms and Conditions"),
                        ("/privacy", "Privacy Policy")]:
        assert path in destinations
        response = client.get(path)
        assert response.status_code == 200
        assert title in response.get_data(as_text=True)
    response = client.post("/logout", data={"csrf_token": page.token})
    assert response.status_code == 302
    assert client.get("/analytics").headers["Location"] == "/login"
