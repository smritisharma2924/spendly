import hmac
import os
import secrets
from datetime import datetime

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


# Transaction history — owned by implementation subagent 1.
def build_profile_transactions(user_id):
    """Prepare the latest transaction rows for the profile template."""
    transactions = []
    for transaction in profile_queries.get_recent_transactions(user_id):
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


# Summary stats — owned by implementation subagent 2.
def build_profile_summary(user_id):
    """Prepare the three spending overview cards."""
    summary = profile_queries.get_summary_stats(user_id)
    return [
        {"label": "Total spent", "value": profile_currency(summary["total_spent"])},
        {"label": "Transactions", "value": str(summary["transaction_count"])},
        {"label": "Top category", "value": summary["top_category"]},
    ]


# Category breakdown — owned by implementation subagent 3.
def build_profile_categories(user_id):
    """Prepare category totals and percentages for the profile template."""
    return [
        {
            "name": category["name"],
            "total": category["amount"],
            "pct": category["pct"],
            "category_class": profile_category_class(category["name"]),
        }
        for category in profile_queries.get_category_breakdown(user_id)
    ]


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
    dashboard = {
        "user": user,
        "summary": build_profile_summary(user_id),
        "transactions": build_profile_transactions(user_id),
        "categories": build_profile_categories(user_id),
    }
    return render_template("profile.html", dashboard=dashboard)


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
