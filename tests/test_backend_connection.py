"""Profile query contracts against isolated SQLite data."""

import sqlite3
from contextlib import closing
from decimal import Decimal

import pytest

from database import db, queries


@pytest.fixture
def user_id(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "backend.db")
    db.init_db()
    db.seed_db()
    return db.get_user_by_email("demo@spendly.com")["id"]


def replace_expenses(user_id, rows):
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute("DELETE FROM expenses WHERE user_id = ?", (user_id,))
            connection.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, "
                "description) VALUES (?, ?, ?, ?, ?)",
                [(user_id,) + row for row in rows],
            )


def test_account_lookup_has_public_fields_and_formatted_date(user_id):
    with closing(db.get_db()) as connection:
        with connection:
            connection.execute(
                "UPDATE users SET created_at = ? WHERE id = ?",
                ("2026-01-15 10:30:00", user_id),
            )
    assert queries.get_user_by_id(user_id) == {
        "name": "Demo User", "email": "demo@spendly.com",
        "member_since": "January 2026",
    }
    assert queries.get_user_by_id(999999) is None


def test_seed_totals_and_categories(user_id):
    assert queries.get_summary_stats(user_id) == {
        "total_spent": Decimal("235.50"), "transaction_count": 8,
        "top_category": "Bills",
    }
    categories = queries.get_category_breakdown(user_id)
    assert [(row["name"], row["amount"]) for row in categories] == [
        ("Bills", 75), ("Shopping", 45), ("Food", Decimal("37.50")),
        ("Health", 30), ("Transport", 20), ("Entertainment", 18), ("Other", 10),
    ]
    assert all(type(row["pct"]) is int for row in categories)
    assert sum(row["pct"] for row in categories) == 100
    assert len(queries.get_recent_transactions(user_id)) == 8


def test_empty_account_is_isolated_from_demo(user_id):
    other_id = db.create_user("Empty", "empty@example.com", "password123")
    assert queries.get_summary_stats(other_id) == {
        "total_spent": 0, "transaction_count": 0, "top_category": "—",
    }
    assert queries.get_recent_transactions(other_id) == []
    assert queries.get_category_breakdown(other_id) == []
    assert queries.get_summary_stats(user_id)["transaction_count"] == 8


def test_history_limit_date_id_order_and_all_time_aggregation(user_id):
    rows = [(1, "Food", "2020-01-01", "Oldest")]
    rows += [(2, "Food", "2026-01-01", "Row {}".format(n)) for n in range(11)]
    rows += [(3, "Bills", "2030-01-01", "Newest")]
    replace_expenses(user_id, rows)
    history = queries.get_recent_transactions(user_id)
    assert len(history) == 10
    assert [row["description"] for row in history] == ["Newest"] + [
        "Row {}".format(n) for n in range(10, 1, -1)
    ]
    assert len(queries.get_recent_transactions(user_id, limit=20)) == 13
    assert queries.get_recent_transactions(user_id, limit=0) == []
    assert queries.get_summary_stats(user_id) == {
        "total_spent": 26, "transaction_count": 13, "top_category": "Food",
    }
    assert queries.get_category_breakdown(user_id)[0]["amount"] == 23


@pytest.mark.parametrize("limit", [-1, True, "10", 1.5])
def test_invalid_limits_are_rejected(user_id, limit):
    with pytest.raises(ValueError):
        queries.get_recent_transactions(user_id, limit)


def test_aggregation_ties_rounding_and_unknown_categories(user_id):
    replace_expenses(user_id, [
        (0.10, "Zebra", "2026-01-01", None),
        (0.20, "Zebra", "2026-01-02", None),
        (0.30, "Alpha", "2026-01-03", None),
        (0.30, "Beta", "2026-01-04", None),
    ])
    assert queries.get_summary_stats(user_id)["top_category"] == "Alpha"
    assert queries.get_category_breakdown(user_id) == [
        {"name": "Alpha", "amount": Decimal("0.30"), "pct": 34},
        {"name": "Beta", "amount": Decimal("0.30"), "pct": 33},
        {"name": "Zebra", "amount": Decimal("0.30"), "pct": 33},
    ]


def test_fractional_cents_and_zero_total(user_id):
    replace_expenses(user_id, [
        (1.005, "Food", "2026-01-01", None),
        (1.005, "Food", "2026-01-02", None),
    ])
    assert queries.get_summary_stats(user_id)["total_spent"] == Decimal("2.02")
    assert queries.get_category_breakdown(user_id)[0]["amount"] == Decimal("2.02")
    assert all(row["amount"] == Decimal("1.01")
               for row in queries.get_recent_transactions(user_id))
    replace_expenses(user_id, [(0, "Food", "2026-01-01", None)])
    assert queries.get_category_breakdown(user_id) == [
        {"name": "Food", "amount": 0, "pct": 0},
    ]


@pytest.mark.parametrize("helper", [
    queries.get_user_by_id, queries.get_summary_stats,
    queries.get_recent_transactions, queries.get_category_breakdown,
])
def test_connections_close_on_success_and_query_failure(user_id, monkeypatch, helper):
    opened = []

    def tracked_connection():
        connection = db.get_db()
        opened.append(connection)
        return connection

    monkeypatch.setattr(queries, "get_db", tracked_connection)
    helper(user_id)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")

    with closing(db.get_db()) as connection:
        connection.execute("DROP TABLE expenses")
        connection.execute("DROP TABLE users")
        connection.commit()
    with pytest.raises(sqlite3.OperationalError):
        helper(user_id)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[-1].execute("SELECT 1")


def test_query_parameters_cannot_select_other_users(user_id):
    assert queries.get_user_by_id("1 OR 1=1") is None
    assert queries.get_summary_stats("1 OR 1=1")["transaction_count"] == 0
    assert queries.get_recent_transactions("1 OR 1=1") == []
    assert queries.get_category_breakdown("1 OR 1=1") == []
