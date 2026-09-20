from flask import Flask, redirect, render_template, request, url_for

from database.db import DuplicateEmailError, create_user, init_db, seed_db

app = Flask(__name__)

with app.app_context():
    init_db()
    seed_db()


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


@app.route("/login")
def login():
    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
