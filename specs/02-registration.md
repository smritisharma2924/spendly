# Spec: Registration

## Overview

Implement the registration form's POST handler. Validate the submitted name, email, and password, reject duplicate emails, hash the password, and save the new user. Show validation errors in the form and redirect successful registrations to the login page.

## Depends on

- Step 1: Database Setup (`specs/01-database-setup.md`), including the users table and the existing `get_db()`, `init_db()`, and `seed_db()` helpers. These are implemented in the current code, despite outdated database descriptions in `AGENTS.md`.
- The existing registration template, shared layout, and login page.

## Routes

- `POST /register` — validate the submitted form and create a user, then redirect to `/login` — access level (`public`).

Add POST support to the existing `/register` handler in `app.py`; its existing GET behavior continues to render the registration form. No additional URL paths are required.

## Database changes

No database changes.

The existing users table already provides `id`, `name`, unique `email`, `password_hash`, and `created_at`. Add query helpers to `database/db.py`, without changing the schema or seed data.

## Templates

- Create: None.
- Modify: `templates/register.html` — use `url_for('register')` for the form action, retain the submitted name and email after validation errors, display errors through the existing error block, add `minlength="8"` to the password input, and add a required `confirm_password` password input. Always render both password fields empty. Preserve the current layout and existing login link.

## Files to change

- `app.py` — extend the registration handler to accept GET and POST, validate form fields, call the database helper, render validation errors, and redirect successful submissions with `url_for('login')`.
- `database/db.py` — add a registration helper that checks for an existing email, hashes the password with Werkzeug, inserts the user, and reports duplicate-email conflicts to the route.
- `templates/register.html` — update the form action, validation attributes, and retained nonsecret field values.

## Files to create

- `tests/test_registration.py` — test registration requests, validation, duplicate handling, password hashing, and persistence using a temporary SQLite database and Flask's test client.

## New dependencies

No new dependencies.

Use the existing Flask, Werkzeug, and pytest packages plus Python's standard-library SQLite support.

## Rules for implementation

- No SQLAlchemy or other ORM; use the project's existing SQLite database approach.
- Use parameterized SQL queries only, with `?` placeholders for supplied values.
- Hash passwords with Werkzeug's `generate_password_hash()`; never store or log plaintext passwords. Verify hashes in tests with `check_password_hash()`.
- Use CSS variables rather than hardcoded hex color values if styling changes are necessary; reuse the existing form styles.
- All application templates must extend `base.html`.
- Keep all routes in `app.py`, with no blueprints. Keep handlers thin and all SQL, transactions, and connection management in `database/db.py`.
- Follow the existing connection lifecycle using `get_db()` and `contextlib.closing`. Preserve `sqlite3.Row` and foreign-key enforcement, commit successful writes, and roll back failed writes.
- Read missing form fields safely. Require a nonempty name after trimming surrounding whitespace, a valid email, and a password of at least eight characters. Validate on the server even when browser validation is bypassed.
- Trim surrounding whitespace from email and store it in lowercase. For this step, email validation requires exactly one `@`, nonempty local and domain parts, and no whitespace; this checks format only, not mailbox ownership.
- Treat email addresses as case-insensitive for duplicate detection, including existing mixed-case records. Check and insert within one write transaction so concurrent registration attempts cannot bypass that check. Preserve the existing unique constraint and handle email conflicts without masking unrelated database failures.
- Do not trim or otherwise transform either password field. Require `confirm_password` and compare it exactly with the password before calling the database helper. Missing or empty confirmation displays “Please confirm your password.”; a mismatch displays “Passwords do not match.” Both return HTTP 400 without inserting a user. Never store, log, or repopulate the confirmation password.
- Render invalid submissions with a clear error and HTTP 400; render duplicate-email submissions with a clear error and HTTP 409. Neither outcome creates a user. Preserve name and email through normal escaped Jinja values, and never return the password in the form or an error message.
- After a successful insert, return an HTTP 302 redirect to the existing login page. Do not automatically sign in the user or create expenses for the new account. Login POST handling, logout, profiles, and expense routes are outside this step.
- Use `url_for()` for new or touched internal links and form actions. Follow PEP 8 and existing Python naming conventions; any JavaScript must remain vanilla JS.
- No new pip packages or changes to `requirements.txt` are needed. Do not introduce a higher Python version requirement or hardcoded secrets.
- Tests must redirect `database.db.DB_PATH` to a temporary database before importing `app.py`, because application startup initializes and seeds the database. Never modify the developer's local database during tests.
- Follow the project subagent policy during implementation: research with an exploration subagent before implementation and have a separate subagent verify test results afterward.

## Definition of done

- [ ] `GET /register` returns HTTP 200 and displays name, email, password, and confirm-password inputs with a working POST form action.
- [ ] Submitting a valid new account returns HTTP 302 with a location resolving to `/login`; following the redirect displays the existing login page.
- [ ] A successful submission creates exactly one user with the trimmed name, lowercase trimmed email, generated ID, and populated creation timestamp; a new database connection can read the committed record.
- [ ] The stored password is a Werkzeug hash rather than plaintext, and `check_password_hash()` accepts the exact submitted password and rejects an incorrect password.
- [ ] Missing fields, whitespace-only names, malformed emails, and passwords shorter than eight characters return HTTP 400 with a visible validation error and create no users. Tests include requests that bypass browser validation.
- [ ] An otherwise valid eight-character password is accepted, and a valid password containing surrounding spaces is preserved exactly when hashed.
- [ ] Matching passwords allow registration; missing, empty, or mismatched confirmation returns HTTP 400 with a visible error, retains name and email, clears both password fields, and creates no user.
- [ ] An existing email, including case and surrounding-whitespace variations and a preexisting mixed-case email, returns HTTP 409 with a visible error and leaves existing account data unchanged.
- [ ] Repeated or concurrent submissions for the same normalized email create at most one account, with subsequent attempts reported as duplicate-email conflicts.
- [ ] Validation errors retain the submitted name and email safely, render HTML-like input as text, and never repopulate or expose the password.
- [ ] Registration creates no authenticated session and does not change existing users or expense records; refreshing the redirected login page creates no additional account.
- [ ] `python -m pytest tests/test_registration.py` and the full `python -m pytest` suite pass using temporary databases, leaving the local database unchanged.
