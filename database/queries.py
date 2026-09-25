"""Read-only profile queries, independent of Flask request and session state."""

from contextlib import closing
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from database.db import get_db


def _money(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_user_by_id(user_id):
    """Return public account details, or None for an absent user."""
    with closing(get_db()) as connection:
        row = connection.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        created = datetime.strptime(row["created_at"][:10], "%Y-%m-%d")
        member_since = created.strftime("%B %Y")
    except (TypeError, ValueError):
        member_since = "—"
    return {
        "name": row["name"], "email": row["email"],
        "member_since": member_since,
    }


def _expense_totals(user_id):
    """Aggregate one user's rows with consistent cent rounding."""
    with closing(get_db()) as connection:
        rows = connection.execute(
            "SELECT category, amount FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    totals = {}
    for row in rows:
        category = row["category"]
        totals[category] = totals.get(category, Decimal("0.00")) + _money(
            row["amount"],
        )
    categories = sorted(
        ({"name": name, "amount": amount} for name, amount in totals.items()),
        key=lambda category: (-category["amount"], category["name"]),
    )
    return len(rows), sum(totals.values(), Decimal("0.00")), categories


def get_summary_stats(user_id):
    """Return all-time spending, count, and the highest-spending category."""
    count, total, categories = _expense_totals(user_id)
    return {
        "total_spent": total,
        "transaction_count": count,
        "top_category": categories[0]["name"] if categories else "—",
    }


def get_recent_transactions(user_id, limit=10):
    """Return newest expenses first, resolving equal dates by descending ID."""
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    with closing(get_db()) as connection:
        rows = connection.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(row, amount=_money(row["amount"])) for row in rows]


def get_category_breakdown(user_id):
    """Return ordered category totals and integer shares of all-time spending."""
    _, total, categories = _expense_totals(user_id)
    for category in categories:
        category["pct"] = (
            int((category["amount"] * 100 / total).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP,
            )) if total else 0
        )
    if total and categories:
        categories[0]["pct"] += 100 - sum(row["pct"] for row in categories)
    return categories
