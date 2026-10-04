import hmac
import os
import re
import secrets
from datetime import date, datetime, timedelta

from flask import (
    Flask, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from database import queries as profile_queries
from database.db import (
    DuplicateEmailError, create_user, get_user_by_email, get_user_by_id,
    init_db, seed_db,
)


CATEGORY_CLASSES = {
    "Food": "food", "Transport": "transport", "Bills": "bills",
    "Health": "health", "Entertainment": "entertainment",
    "Shopping": "shopping", "Other": "other",
}

app = Flask(__name__)
secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError("Set a nonempty SECRET_KEY environment variable.")

secure_cookie = os.environ.get("SESSION_COOKIE_SECURE", "false").lower()
if secure_cookie not in ("true", "false", "1", "0"):
    raise RuntimeError("SESSION_COOKIE_SECURE must be true, false, 1, or 0.")
app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=secure_cookie in ("true", "1"),
)

with app.app_context():
    init_db()
    seed_db()


@app.before_request
def load_current_user():
    g.user = None
    if "user_id" not in session:
        return
    user_id = session["user_id"]
    if type(user_id) is not int or not 0 < user_id <= 9223372036854775807:
        session.clear()
        return
    g.user = get_user_by_id(user_id)
    if g.user is None:
        session.clear()


@app.template_global()
def csrf_token():
    """Create a token only when a rendered form needs one."""
    current = session.get("csrf_token")
    if not isinstance(current, str) or not current:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def valid_csrf_token():
    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token")
    return (
        isinstance(expected, str) and bool(expected)
        and isinstance(supplied, str)
        and hmac.compare_digest(
            expected.encode("utf-8"), supplied.encode("utf-8"),
        )
    )


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html")


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method != "POST":
        return render_template("register.html", name="", email="")

    submitted_name = request.form.get("name", "")
    submitted_email = request.form.get("email", "")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    name = submitted_name.strip()
    email = submitted_email.strip().lower()
    local_part, separator, domain = email.partition("@")

    error = None
    status = 400
    if not name:
        error = "Please enter your name."
    elif (
        not separator or not local_part or not domain or "@" in domain
        or any(character.isspace() for character in email)
    ):
        error = "Please enter a valid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif not confirm_password:
        error = "Please confirm your password."
    elif password != confirm_password:
        error = "Passwords do not match."
    else:
        try:
            create_user(name, email, password)
        except DuplicateEmailError:
            error = "An account with this email already exists."
            status = 409
        else:
            return redirect(url_for("login"))

    return render_template(
        "register.html", error=error,
        name=submitted_name, email=submitted_email,
    ), status


@app.route("/login", methods=["GET", "POST"])
def login():
    submitted_email = request.form.get("email", "")
    if request.method == "POST" and not valid_csrf_token():
        return render_template(
            "login.html", email=submitted_email,
            error="Your form has expired. Please try again.",
        ), 400
    if g.user is not None:
        return redirect(url_for("profile"))
    if request.method != "POST":
        return render_template("login.html", email="")

    email = submitted_email.strip().lower()
    password = request.form.get("password", "")
    local_part, separator, domain = email.partition("@")
    if (
        not separator or not local_part or not domain or "@" in domain
        or any(character.isspace() for character in email)
    ):
        error = "Please enter a valid email address."
    elif not password:
        error = "Please enter your password."
    else:
        user = get_user_by_email(email)
        if user is not None and check_password_hash(
            user["password_hash"], password,
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("profile"))
        flash("Invalid email or password.", "error")
        return render_template("login.html", email=submitted_email), 401

    return render_template(
        "login.html", email=submitted_email, error=error,
    ), 400


@app.route("/logout", methods=["POST"])
def logout():
    if not valid_csrf_token():
        abort(400)
    session.clear()
    return redirect(url_for("login"))


# Profile presentation helpers shared by the three spending sections.
def profile_date(value):
    """Parse a stored ISO date or timestamp, allowing missing legacy values."""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def profile_category_class(category):
    return CATEGORY_CLASSES.get(category, "other")


def profile_currency(amount):
    return "₹{:,.2f}".format(amount)


def build_profile_transactions(user_id, start_date=None, end_date=None):
    """Prepare the latest transaction rows for the profile template."""
    transactions = []
    for transaction in profile_queries.get_recent_transactions(
        user_id, start_date=start_date, end_date=end_date,
    ):
        transaction_date = profile_date(transaction["date"])
        description = transaction["description"]
        transactions.append({
            "date": transaction_date.isoformat() if transaction_date else None,
            "date_label": (
                transaction_date.strftime("%d %b %Y")
                if transaction_date else "—"
            ),
            "description": (
                description if description and description.strip() else "—"
            ),
            "category": transaction["category"],
            "category_class": profile_category_class(transaction["category"]),
            "amount": transaction["amount"],
        })
    return transactions


def build_profile_summary(user_id, start_date=None, end_date=None):
    """Prepare the three spending overview cards."""
    summary = profile_queries.get_summary_stats(
        user_id, start_date=start_date, end_date=end_date,
    )
    return [
        {"label": "Total spent", "value": profile_currency(summary["total_spent"])},
        {"label": "Transactions", "value": str(summary["transaction_count"])},
        {"label": "Top category", "value": summary["top_category"]},
    ]


def build_profile_categories(user_id, start_date=None, end_date=None):
    """Prepare category totals and percentages for the profile template."""
    return [
        {
            "name": category["name"],
            "total": category["amount"],
            "pct": category["pct"],
            "category_class": profile_category_class(category["name"]),
        }
        for category in profile_queries.get_category_breakdown(
            user_id, start_date=start_date, end_date=end_date,
        )
    ]


def profile_date_presets(today=None):
    """Return ranges for complete calendar months before the current month."""
    today = today if today is not None else date.today()
    first_day = today.replace(day=1)
    end_date = (first_day - timedelta(days=1)).isoformat()
    presets = []
    for label, months in (("Last Month", 1), ("Last 3 Months", 3),
                          ("Last 6 Months", 6)):
        month_index = first_day.year * 12 + first_day.month - 1 - months
        year, month = divmod(month_index, 12)
        presets.append({
            "label": label,
            "start_date": date(year, month + 1, 1).isoformat(),
            "end_date": end_date,
        })
    return presets


def validate_profile_dates(parameters):
    """Return valid ISO bounds and field errors without normalizing bad input."""
    bounds = {"start_date": None, "end_date": None}
    errors = {}
    for field, label in (("start_date", "Start date"), ("end_date", "End date")):
        value = parameters.get(field, "")
        if not value:
            continue
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                raise ValueError
            date(*map(int, value.split("-")))
        except ValueError:
            errors[field] = label + " must be a real date in YYYY-MM-DD format."
        else:
            bounds[field] = value
    if (bounds["start_date"] and bounds["end_date"]
            and bounds["start_date"] > bounds["end_date"]):
        errors["end_date"] = "End date must be on or after start date."
    return bounds, errors


@app.route("/analytics")
def analytics():
    if g.user is None:
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/profile")
def profile():
    if g.user is None:
        return redirect(url_for("login"))
    user_id = g.user["id"]
    user = profile_queries.get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))
    name_parts = user["name"].split()
    initials = "?"
    if name_parts:
        initials = name_parts[0][0]
        if len(name_parts) > 1:
            initials += name_parts[-1][0]
        initials = initials.upper()[:2]
    joined = profile_date(g.user["created_at"])
    user.update(
        name=user["name"] if name_parts else "Your profile",
        initials=initials,
        member_since_iso=joined.isoformat() if joined else None,
    )
    bounds, filter_errors = validate_profile_dates(request.args)
    dashboard = {"user": user}
    if not filter_errors:
        dashboard.update(
            summary=build_profile_summary(user_id, **bounds),
            transactions=build_profile_transactions(user_id, **bounds),
            categories=build_profile_categories(user_id, **bounds),
        )
    return render_template(
        "profile.html", dashboard=dashboard, date_filter=bounds,
        filter_errors=filter_errors, is_filtered=any(bounds.values()),
        date_presets=profile_date_presets(),
    ), 400 if filter_errors else 200


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
