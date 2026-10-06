# Spec: Add Expense

## Overview

Allow signed-in users to record an expense with an INR amount, category, date, and optional description, then return to their profile to see updated spending. Step 07 replaces the existing add-expense stub with a validated form and a committed SQLite insert, building on the live profile and date filtering introduced in Steps 05 and 06. Expense editing and deletion remain later steps.

## Depends on

- Step 01: Database Setup — the existing `expenses` table and configured SQLite connection helpers.
- Step 02: Registration and Step 03: Login and Logout — user accounts, resolved session identity, and session-bound CSRF helpers.
- Step 04: Profile Page and Step 05: Backend Connection — profile templates and user-scoped spending queries.
- Step 06: Date Filter for Profile Page — preserve the implemented date filtering when newly recorded expenses are displayed.

## Routes

- `POST /expenses/add` — validate and save an expense for the authenticated user, then redirect to the profile — access level (`logged-in`).

Add POST support to the existing `add_expense` handler. Its existing `GET /expenses/add` becomes a logged-in form page instead of a raw-string stub. No new URL paths are required.

## Database changes

No database changes.

The existing `expenses` table already contains `id`, `user_id` referencing `users.id`, `amount REAL`, `category TEXT`, `date TEXT`, nullable `description`, and a default `created_at` timestamp. Add a write helper in `database/db.py`; preserve the schema, seed data, and read-only responsibilities of `database/queries.py`.

## Templates

- Create: `templates/add_expense.html` — extend `base.html`; render labeled Amount (₹), Category, Date, and optional Description fields, a hidden CSRF token, Save expense button, Cancel link, and accessible validation feedback. Load page styles through the `head` block.
- Modify: `templates/profile.html` — add an Add expense link near the spending heading, visible even for empty data or invalid date filters, and display the success flash after saving. Preserve the existing filters, account details, and spending sections.

## Files to change

- `app.py` — implement authenticated GET/POST behavior, validate form input and CSRF, call the write helper, and redirect after success.
- `database/db.py` — add `create_expense(user_id, amount, category, expense_date, description=None)` to insert validated data and return the generated expense ID.
- `templates/profile.html` — expose the add form and render success feedback.
- `static/css/profile.css` — style the Add expense link and success notice using existing variables and responsive layout conventions.

## Files to create

- `templates/add_expense.html` — the server-rendered expense form with retained values and errors.
- `static/css/expense.css` — scoped form layout, validation, and responsive styles using existing shared form classes where practical.
- `tests/test_add_expense.py` — isolated helper, route, validation, authentication, CSRF, and profile integration tests.

## New dependencies

No new dependencies.

Use existing Flask, SQLite, and pytest facilities, plus standard-library `decimal` and date validation.

## Rules for implementation

- No SQLAlchemy or other ORM; use the project's existing database approach. Use parameterized SQL queries only, with `?` placeholders.
- Hash passwords with Werkzeug when passwords are involved; this feature requires no password changes.
- Use CSS variables rather than hardcoded hex color values and preserve the no-inline-styles convention. All application templates must extend `base.html`.
- Keep routes in `app.py`, without blueprints, and keep handlers thin. Put SQL, transaction handling, and connection management in `database/db.py`. The new helper accepts validated values and has no dependency on Flask request or session state.
- Use `get_db()` with `contextlib.closing`, preserving `sqlite3.Row` and foreign-key enforcement. Commit the insert before returning its ID, roll back failed writes, and close the connection on success and failure. Supply only `user_id`, `amount`, `category`, `date`, and `description`; let SQLite generate `id` and `created_at`. Do not mask unexpected database failures as successful saves or input errors.
- For both GET and POST, check `g.user` before processing form input. Anonymous users and invalid or stale sessions redirect with HTTP 302 to `url_for('login')`, without inserting an expense. Obtain ownership exclusively from `g.user['id']`; ignore submitted or query-string user IDs.
- Reuse `csrf_token()` and `valid_csrf_token()`. Authenticated POST requests with a missing, incorrect, or another session's token return HTTP 400, render the form with an expiration error, and perform no write. Keep the expense and navigation logout forms separate, and preserve login token rotation.
- GET returns HTTP 200 with blank amount and description, an unselected required category placeholder, and Date defaulted to the server's current local date. Reading or refreshing the form never inserts data.
- Use form names `amount`, `category`, `date`, and `description`. Read missing fields safely and validate on the server even when browser validation is bypassed. Trim surrounding whitespace from amount and description; do not normalize category or date values.
- Amount is required and represents INR. Accept only ASCII digits with an optional decimal point followed by one or two digits, after trimming. Allow values from `0.01` through `999999999.99`, inclusive. Validate with `Decimal` before converting to a float for the existing SQLite REAL column. Reject zero, negatives, signs, exponent notation, commas, currency symbols, nonfinite values, more than two decimal places, and values outside the range; do not silently round invalid precision. Examples: `12`, `12.5`, and `12.50` are valid; `.50`, `12.`, `1e2`, and `12.345` are invalid. State the range in the form and use suitable `min`, `max`, and `step="0.01"` attributes.
- Category is required and must exactly match one of `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`, or `Other`. Reuse the existing category vocabulary in `app.py` for the select options and server validation; reject arbitrary or differently cased categories. Do not add a category table or custom categories.
- Date is required and must be a real calendar date in exact zero-padded `YYYY-MM-DD` format. Reject impossible dates, invalid leap days, timestamps, and surrounding whitespace. Accept past, present, and future dates, consistent with the existing seed data and Step 06. Use a native date input; do not use the permissive stored-date presentation parser for validating requests.
- Description is optional. After trimming, accept at most 500 characters; store an omitted, empty, or whitespace-only description as `NULL`. Reject longer descriptions instead of truncating them. Include `maxlength="500"` and identify the field as optional.
- Invalid fields return HTTP 400 using `add_expense.html`, with clear field-specific errors and no insert. Preserve submitted amount and description as escaped text, plus valid selected category and date values. Malformed number/date values may appear blank in native controls, but identify the affected field; never substitute today's date after a failed submission. Never inject an unrecognized category into the option list. Do not apply Jinja's `safe` filter to user data.
- After one successful insert, flash “Expense added successfully.” with category `success` and return HTTP 302 to `url_for('profile')` without date parameters. Display the message once using an accessible status notice. Refreshing this destination must not repeat the insert. Each separate valid POST creates an expense; duplicate-submission prevention beyond POST/redirect/GET is outside this step.
- The unfiltered profile must incorporate the saved expense into total spending, transaction count, and category totals. Its latest-ten table keeps `date DESC, id DESC` ordering, so an older saved expense may fall outside the visible ten. Existing date filters include the expense only when its date matches the range; retain all-time defaults, INR formatting, and query rounding behavior.
- Use `url_for()` for new or touched links, actions, and redirects. Cancel links to the unfiltered profile and performs no write. The form must work without JavaScript, with associated labels, visible focus, errors linked to inputs, and usable controls at mobile and desktop widths.
- Preserve existing authentication and profile behavior. Do not implement edit/delete stubs, custom categories, recurring expenses, uploads, schema migrations, or analytics functionality in this step. Follow PEP 8 and existing naming conventions; any JavaScript remains vanilla. Do not install packages, change `requirements.txt`, implicitly raise the Python minimum, or introduce hardcoded secrets.
- Tests must patch `database.db.DB_PATH` to a temporary SQLite file before importing the app, set test-only `SECRET_KEY` and `SESSION_COOKIE_SECURE`, and initialize the temporary schema for each test even when the app module is cached. Restore mutable configuration using `monkeypatch`, close connections, and obtain real CSRF tokens for valid POST requests. Never read or mutate the developer's database or `.env`.
- During implementation, use an exploration subagent before coding and a separate subagent to verify test results afterward. Report conflicts with existing specifications or tests rather than weakening assertions or reverting completed features.

## Definition of done

- [ ] The profile's Add expense link opens an authenticated form with the four specified fields, exact seven categories, today's date, a CSRF token, Save expense, and Cancel. It remains accessible when the profile has no expenses or an invalid date filter.
- [ ] Anonymous, malformed-session, and deleted-account GET and POST requests redirect to login and leave expenses unchanged, including requests containing invalid form data.
- [ ] A valid authenticated submission returns HTTP 302 to `/profile` and commits exactly one expense with the authenticated user's ID, expected values, generated ID, and populated creation timestamp, readable through a fresh connection.
- [ ] Amounts `0.01`, `12`, `12.5`, `12.50`, and `999999999.99` are accepted; blank, zero, negative, signed, malformed, nonfinite, exponent, excessive-precision, and over-limit values return HTTP 400 without writes. Surrounding amount whitespace is trimmed.
- [ ] Every fixed category is accepted. Missing, unknown, differently cased, or whitespace-padded categories return HTTP 400 without inserting data.
- [ ] Valid past, current, future, and leap-day dates are accepted. Missing, impossible, non-zero-padded, whitespace-padded, timestamp, and invalid leap-day values return HTTP 400 without writes.
- [ ] Omitted or whitespace-only descriptions persist as NULL; a trimmed 500-character description succeeds and 501 characters fails. Quotes and HTML-like text remain data and display escaped in the form and profile.
- [ ] Field errors identify the invalid input, retain correctable values as specified, and never reset a submitted invalid date to today. Missing or incorrect CSRF tokens, another client's token, and a token from before login all fail with HTTP 400 and no insert.
- [ ] A forged user ID in the URL or form cannot change expense ownership. Two users see only their own saved expenses and spending totals.
- [ ] Following a successful redirect shows the success message once and updated all-time totals. A qualifying expense appears in the latest-ten table in the existing order; an older expense outside that limit still contributes to totals. Date ranges include and exclude the expense correctly.
- [ ] GET, HEAD, Cancel, invalid POST, and refreshing the successful redirect do not create expenses. Saving does not modify users or existing expense rows, and a simulated database failure cannot produce a success redirect or partial write.
- [ ] The form submits without JavaScript. Keyboard navigation, labels, focus indicators, and validation feedback are usable; at 375px and desktop widths the form introduces no page-level horizontal overflow. Login and the separate CSRF-protected logout form remain functional.
- [ ] `python -m pytest tests/test_add_expense.py` and the full `python -m pytest` suite pass with temporary databases, including unchanged seed-only profile expectations before any expense is added.
