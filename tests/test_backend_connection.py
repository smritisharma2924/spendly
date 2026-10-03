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


@pytest.mark.parametrize("start,end,descriptions,total", [
    ("2024-02-29", "2024-03-02", ["End", "Middle", "Start"], "9.00"),
    ("2024-02-29", "2024-02-29", ["Start"], "2.00"),
    ("2024-03-02", None, ["After", "End"], "9.00"),
    (None, "2024-02-29", ["Start", "Before"], "3.00"),
    (None, None, ["After", "End", "Middle", "Start", "Before"], "15.00"),
    ("2050-01-01", "2050-12-31", [], "0.00"),
])
def test_inclusive_bounds_apply_to_every_section(user_id, start, end, descriptions, total):
    rows = [
        (1, "Food", "2024-02-28", "Before"),
        (2, "Food", "2024-02-29", "Start"),
        (3, "Food", "2024-03-01", "Middle"),
        (4, "Food", "2024-03-02", "End"),
        (5, "Food", "2099-01-01", "After"),
    ]
    replace_expenses(user_id, rows)
    other_id = db.create_user("Other", "other@example.com", "secret123")
    replace_expenses(other_id, rows)
    bounds = {"start_date": start, "end_date": end}
    assert queries.get_summary_stats(user_id, **bounds) == {
        "total_spent": Decimal(total), "transaction_count": len(descriptions),
        "top_category": "Food" if descriptions else "—",
    }
    assert [row["description"] for row in queries.get_recent_transactions(
        user_id, **bounds,
    )] == descriptions
    assert queries.get_category_breakdown(user_id, **bounds) == ([
        {"name": "Food", "amount": Decimal(total), "pct": 100},
    ] if descriptions else [])


def test_filtered_limit_order_and_full_aggregation(user_id):
    rows = [(999, "Other", "2023-12-31", "Outside before")]
    rows += [(2, "Food", "2024-01-01", "Row {}".format(n)) for n in range(11)]
    rows += [(3, "Bills", "2024-01-02", "Newest match")]
    rows += [(999, "Other", "2025-01-01", "Outside after")]
    replace_expenses(user_id, rows)
    bounds = {"start_date": "2024-01-01", "end_date": "2024-12-31"}
    history = queries.get_recent_transactions(user_id, **bounds)
    assert [row["description"] for row in history] == ["Newest match"] + [
        "Row {}".format(n) for n in range(10, 1, -1)
    ]
    assert len(queries.get_recent_transactions(user_id, 20, **bounds)) == 12
    assert len(queries.get_recent_transactions(user_id, limit=2, **bounds)) == 2
    assert queries.get_recent_transactions(user_id, 0, **bounds) == []
    for invalid in (-1, True, "10", 1.5):
        with pytest.raises(ValueError):
            queries.get_recent_transactions(user_id, invalid, **bounds)
    assert queries.get_summary_stats(user_id, **bounds) == {
        "total_spent": 25, "transaction_count": 12, "top_category": "Food",
    }
    assert queries.get_category_breakdown(user_id, **bounds) == [
        {"name": "Food", "amount": 22, "pct": 88},
        {"name": "Bills", "amount": 3, "pct": 12},
    ]


def test_filtered_rounding_ties_and_zero_totals(user_id):
    replace_expenses(user_id, [
        (1000, "Outside", "2023-01-01", None),
        (0.105, "Zebra", "2024-01-01", None),
        (0.195, "Zebra", "2024-01-02", None),
        (0.31, "Alpha", "2024-01-03", None),
        (0.31, "Beta", "2024-01-04", None),
        (0, "Food", "2025-01-01", None),
    ])
    bounds = {"start_date": "2024-01-01", "end_date": "2024-12-31"}
    assert queries.get_summary_stats(user_id, **bounds) == {
        "total_spent": Decimal("0.93"), "transaction_count": 4, "top_category": "Alpha",
    }
    assert queries.get_category_breakdown(user_id, **bounds) == [
        {"name": "Alpha", "amount": Decimal("0.31"), "pct": 34},
        {"name": "Beta", "amount": Decimal("0.31"), "pct": 33},
        {"name": "Zebra", "amount": Decimal("0.31"), "pct": 33},
    ]
    assert [row["amount"] for row in queries.get_recent_transactions(user_id, **bounds)] == [
        Decimal("0.31"), Decimal("0.31"), Decimal("0.20"), Decimal("0.11"),
    ]
    assert queries.get_category_breakdown(user_id, start_date="2025-01-01") == [
        {"name": "Food", "amount": 0, "pct": 0},
    ]


@pytest.mark.parametrize("field", ["start_date", "end_date"])
def test_date_bounds_are_bound_parameters(user_id, field):
    replace_expenses(user_id, [(1, "Food", "2024-01-01", None)])
    # A literal containing SQL syntax must neither broaden the range nor execute.
    value = "9999' OR 1=1 --" if field == "start_date" else "0000' OR 1=1 --"
    bounds = {field: value}
    assert queries.get_summary_stats(user_id, **bounds)["transaction_count"] == 0
    assert queries.get_recent_transactions(user_id, **bounds) == []
    assert queries.get_category_breakdown(user_id, **bounds) == []
    assert queries.get_summary_stats(user_id)["transaction_count"] == 1


def test_filtered_queries_keep_users_with_same_dates_isolated(user_id):
    replace_expenses(user_id, [
        (2, "Food", "2024-02-29", "Own boundary"),
        (3, "Bills", "2024-03-01", "Own outside"),
    ])
    other_id = db.create_user("Other", "same-day@example.com", "secret123")
    replace_expenses(other_id, [
        (999, "Shopping", "2024-02-29", "Other boundary"),
    ])
    bounds = {"start_date": "2024-02-29", "end_date": "2024-02-29"}
    assert queries.get_summary_stats(user_id, **bounds) == {
        "total_spent": Decimal("2.00"), "transaction_count": 1,
        "top_category": "Food",
    }
    assert [row["description"] for row in queries.get_recent_transactions(
        user_id, **bounds,
    )] == ["Own boundary"]
    assert queries.get_category_breakdown(user_id, **bounds) == [
        {"name": "Food", "amount": Decimal("2.00"), "pct": 100},
    ]
    assert queries.get_summary_stats(other_id, **bounds)["total_spent"] == 999
