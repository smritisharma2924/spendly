# Spec: Edit Expense

## Overview

Allow signed-in users to correct the amount, category, date, and optional description of their own expenses from the profile's transaction table. Step 08 replaces the edit stub with a prefilled form and a committed, owner-scoped SQLite update, reusing Step 07's validation and form styles while preserving the live spending totals and date filtering from Steps 05 and 06. The current code implements Add Expense even though `AGENTS.md` still describes it as a stub; retain that implementation. Expense deletion remains Step 09.

## Depends on

- Step 01: Database Setup — the existing expenses table and configured SQLite connection helpers.
- Step 02: Registration and Step 03: Login and Logout — accounts, resolved session identity, and session-bound CSRF helpers.
- Step 04: Profile Page and Step 05: Backend Connection — profile layout and user-scoped spending queries.
- Step 06: Date Filter for Profile Page — preserve inclusive ranges, presets, and all-time defaults.
- Step 07: Add Expense — reuse `validate_expense_form()`, `CATEGORY_CLASSES`, `static/css/expense.css`, and the existing profile success notice.

## Routes

- `POST /expenses/<int:id>/edit` — validate and update an expense owned by the authenticated user, then redirect to the profile — access level (`logged-in`).

Add POST support to the existing `edit_expense` handler. Its existing `GET /expenses/<int:id>/edit` becomes a logged-in, prefilled edit form instead of a raw-string stub. No new URL paths are required.

## Database changes

No database changes.

The existing `expenses` table already provides `id`, `user_id`, `amount REAL`, `category TEXT`, `date TEXT`, nullable `description`, and `created_at`. Add owner-scoped lookup and update helpers to `database/db.py`; preserve the schema, seeds, and read-only responsibilities of `database/queries.py`.

## Templates

- Create: `templates/edit_expense.html` — extend `base.html`; render an Edit expense heading, prefilled Amount (₹), Category, Date, and optional Description fields, hidden CSRF token, Save changes button, Cancel link, and accessible validation feedback. Load the existing expense stylesheet through the `head` block and reuse its form classes.
- Modify: `templates/profile.html` — add an Actions column with an Edit link for every displayed transaction, and update the empty-row column span. Give each link an accessible name that identifies its expense. Reuse the existing success notice; preserve account details, add-expense access, filters, and spending sections.

## Files to change

- `app.py` — implement authenticated edit GET/POST behavior, reuse validation and CSRF helpers, call owner-scoped database helpers, and pass each transaction's ID through `build_profile_transactions()`.
- `database/db.py` — add `get_expense_by_id(expense_id, user_id)` and `update_expense(expense_id, user_id, amount, category, expense_date, description=None)`.
- `database/queries.py` — include `id` in `get_recent_transactions()` results while retaining all existing fields, arguments, filtering, rounding, ordering, and limit behavior.
- `templates/profile.html` — expose Edit links and update the transaction table's column structure.
- `static/css/profile.css` — style the Actions column and Edit links with existing CSS variables, visible focus, and the existing horizontal scrolling layout.
- `tests/test_profile.py` — verify correctly targeted Edit links and intentionally adapt four-column cell counts and strides to the Actions column while retaining all existing data, filter, and authentication assertions.
- `tests/test_backend_connection.py` — verify transaction IDs accompany the correct rows without changing ordering, limits, date filtering, or user isolation.

## Files to create

- `templates/edit_expense.html` — the prefilled, server-rendered edit form and error states.
- `tests/test_edit_expense.py` — isolated lookup/update helper, route, ownership, validation, CSRF, and profile integration tests.

## New dependencies

No new dependencies.

Use the existing Flask, SQLite, Werkzeug, pytest, standard-library date/decimal facilities, and expense form styles.

## Rules for implementation

- No SQLAlchemy or other ORM; use the project's existing database approach. Use parameterized SQL queries only, with `?` placeholders for all supplied values.
- Hash passwords with Werkzeug when passwords are involved; this feature requires no password changes.
- Use CSS variables rather than hardcoded hex color values. Preserve the no-inline-styles convention. All application templates must extend `base.html`.
- Keep routes in `app.py`, without blueprints, and keep handlers thin. Put edit lookup, SQL, transaction handling, and connection management in `database/db.py`. Helpers must remain independent of Flask request and session state.
- `get_expense_by_id(expense_id, user_id)` returns the expense row or `None`. Both lookup and update must include `id = ? AND user_id = ?` in SQL. `update_expense(...)` accepts validated values, commits the update, and returns `True` when an owned row matched, including an unchanged submission, or `False` when no row matched. The route must return HTTP 404 for a failed match rather than flashing success. Retain the ownership predicate in the update even after a successful lookup so a changed or removed row cannot bypass it.
- Use `get_db()` with `contextlib.closing`, preserving `sqlite3.Row` and foreign-key enforcement. Commit before reporting success, roll back failed writes, and close connections on success and failure. Update only `amount`, `category`, `date`, and `description`; preserve `id`, `user_id`, and `created_at`. Do not insert a replacement row or mask unexpected database failures as missing data, validation errors, or success.
- For GET and POST, check `g.user` before expense lookup or form processing. Anonymous, invalid-session, and deleted-account requests redirect with HTTP 302 to `url_for('login')` without writes. Obtain the user ID exclusively from `g.user['id']` and the expense ID from the route; ignore form/query attempts to override either identity.
- Authenticated requests for missing or another user's expenses return the same HTTP 404 via `abort(404)`, without exposing their fields or modifying data. Reject route IDs outside SQLite's positive signed 64-bit ID range as HTTP 404 before binding them, including zero and oversized integers; malformed paths retain Flask's normal 404 behavior.
- After confirming ownership, POST must pass `valid_csrf_token()` before field validation or any update. Missing, incorrect, another session's, and pre-login tokens return HTTP 400 with the edit form and “Your form has expired. Please try again.”, without writes. Use `csrf_token()` in the form and keep the navigation logout form separate.
- Owned GET returns HTTP 200 with the stored amount formatted to two decimal places, selected category, stored ISO date, and description (`NULL` displayed as empty). Do not default the edit date to today. GET, HEAD, refresh, and Cancel must never update data.
- Reuse `validate_expense_form()` and `CATEGORY_CLASSES` so add and edit have identical server validation. Keep form names `amount`, `category`, `date`, and `description`; read missing fields safely and validate even when browser checks are bypassed. A missing required field on POST is invalid rather than falling back to the stored value.
- Amount is required, trimmed, and accepts only ASCII digits with an optional decimal point followed by one or two digits. Permit `0.01` through `999999999.99` inclusive; validate with `Decimal` before converting for SQLite REAL storage. Reject zero, negatives, signs, exponent notation, commas, symbols, nonfinite values, excess precision, and out-of-range values without rounding them into validity. Retain `min`, `max`, `step="0.01"`, and range help text.
- Category must exactly match `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`, or `Other`. Reject missing, unknown, differently cased, and whitespace-padded categories. Never inject submitted arbitrary categories into the option list.
- Date is required and must be a real calendar date in exact zero-padded `YYYY-MM-DD` format. Permit past, present, future, and valid leap-day dates; reject impossible dates, timestamps, invalid leap days, surrounding whitespace, and non-zero-padded dates. Use a native date input and the existing strict validator rather than the stored-date presentation parser.
- Description is optional: trim it, accept at most 500 characters, and store omitted, empty, or whitespace-only values as `NULL`, allowing an existing description to be cleared. Reject longer input rather than truncating it; retain `maxlength="500"` and the optional label.
- Invalid fields return HTTP 400 using `edit_expense.html`, with field-specific errors and no update. Retain submitted amount and description as escaped text and valid category/date selections, rather than restoring stored values. Malformed number/date values may appear blank in native controls but must identify the affected field. Do not substitute today's date or apply Jinja's `safe` filter to user data.
- A successful update flashes “Expense updated successfully.” with category `success` and returns HTTP 302 to `url_for('profile')` without date parameters. Display the message once through the existing accessible status notice. Cancel also links to the unfiltered profile without writing. Ignore supplied `next` or return URLs; filter-preserving return navigation and concurrent-edit conflict detection are outside this step.
- An unchanged valid submission succeeds without creating a row or changing identity/timestamps. Refreshing the redirected profile must not repeat the update. Separate valid submissions update the same row; the last successful write takes effect.
- Add the real expense `id` to recent-transaction query dictionaries and profile presentation dictionaries. This intentionally extends Step 05's result shape without removing existing keys. Preserve the positional `limit`, date bounds, `date DESC, id DESC` order, latest-ten limit, Decimal rounding, category ordering, and percentage rules. Edit links use `url_for('edit_expense', id=transaction.id)` for their own rows, including filtered results.
- After editing, all-time transaction count stays constant. Total spending changes by the amount difference, category totals reflect category changes, and date changes alter filtered membership and table order. An expense moved outside the latest ten still contributes to matching totals. Account details and other expenses remain unchanged.
- Use `url_for()` for new or touched internal links, actions, and redirects. The edit form works without JavaScript, with associated labels, visible keyboard focus, errors linked to fields, and usable controls at 375px and desktop widths. Keep existing table scrolling and empty states usable with the extra column.
- Preserve registration, login/logout, add-expense behavior, and profile date filters. Do not implement deletion, analytics, pagination, custom categories, schema migrations, or new packages. Follow PEP 8, existing naming conventions, and vanilla JS constraints; do not change `requirements.txt`, implicitly raise the Python minimum, or introduce hardcoded secrets.
- Tests must patch `database.db.DB_PATH` to a temporary database before importing the app, set test-only `SECRET_KEY` and `SESSION_COOKIE_SECURE`, initialize the temporary schema for each test even when the app module is cached, restore mutable configuration with `monkeypatch`, and close connections. Obtain real CSRF tokens and preserve login rotation. Never read or mutate the developer's database or `.env`.
- During implementation, use an exploration subagent before coding and a separate subagent to verify test results afterward. The Actions column and transaction ID addition require targeted assertion updates; preserve existing behavior checks and report any further conflicts rather than weakening tests or reverting completed features.

## Definition of done

- [ ] Each displayed profile transaction has an Edit link targeting its actual expense ID, including filtered rows. Empty states span all five columns, and date filtering, ordering, limits, and Add expense access remain available.
- [ ] An authenticated owner can open the form and see all stored values, including a two-decimal amount and an empty field for a NULL description, with a CSRF token, Save changes, and Cancel.
- [ ] Anonymous, invalid-session, and deleted-account GET and POST requests redirect to login without writes, including requests with invalid fields or nonexistent expense IDs.
- [ ] Missing, other-user, zero, and oversized IDs return HTTP 404 for authenticated GET and POST requests without exposing fields or changing data. Forged user/expense IDs in form or query parameters cannot change the targeted row or its ownership.
- [ ] A valid submission redirects to `/profile`, shows the success notice once, and commits the four editable fields to exactly the owned row, readable from a fresh connection. Row count, ID, ownership, creation timestamp, users, and unrelated expenses remain unchanged.
- [ ] Submitting the same valid values succeeds without creating a row or changing identity/timestamps. A row removed between lookup and update produces HTTP 404 rather than a success redirect.
- [ ] Amount boundaries `0.01` and `999999999.99`, integers, and one/two-decimal inputs succeed. Missing, zero, negative, signed, nonfinite, exponent, excessive-precision, malformed, and over-limit inputs return HTTP 400 and leave the stored row unchanged.
- [ ] All seven categories succeed; missing, unknown, differently cased, and whitespace-padded values fail with HTTP 400 and no writes. Valid past, present, future, and leap-day dates succeed; missing, impossible, malformed, timestamp, non-zero-padded, and whitespace-padded dates fail similarly.
- [ ] A trimmed 500-character description succeeds; 501 characters fails. Empty, omitted, and whitespace-only descriptions clear an existing description to NULL. Quotes and HTML-like text persist as data and display escaped in the edit form and profile.
- [ ] Validation errors retain submitted correctable values, identify invalid fields, and never replace a submitted date with today or restore the original values. Missing, incorrect, cross-session, and pre-login CSRF tokens return HTTP 400 without writes.
- [ ] Known fixture edits change totals by the expected amount difference, move spending between categories, preserve all-time transaction count, and update date-range membership and latest-ten ordering. Both users continue to see only their own expenses; unchanged seed-only profile expectations still pass.
- [ ] GET, HEAD, Cancel, invalid POST, and refreshing the success destination leave stored expenses unchanged. Simulated database failures roll back changes and cannot yield a success notice or redirect; helper connections close on success and failure.
- [ ] The form works without JavaScript; labels, keyboard navigation, focus indicators, errors, and Edit link names are usable. At 375px and desktop widths the form has no page-level horizontal overflow, and the transaction table remains accessible through its scrolling region. Add expense, login, and CSRF-protected logout remain functional.
- [ ] `python -m pytest tests/test_edit_expense.py tests/test_profile.py tests/test_backend_connection.py` and the full `python -m pytest` suite pass with isolated temporary databases.
