# Spec: Date Filter for Profile Page

## Overview

Add a date-range filter to the existing database-backed profile page so signed-in users can review spending for a chosen period. Step 06 builds on Step 05 by applying the same range to summary statistics, recent transactions, and category breakdowns, while leaving account details unchanged. Visiting the profile without dates continues to show all-time spending. This step adds filtering only; expense creation, editing, and deletion remain later roadmap steps.

## Depends on

- Step 01: Database Setup — the existing SQLite schema, stored expense dates, and connection helpers.
- Step 02: Registration and Step 03: Login and Logout — user accounts, session identity, and authenticated access.
- Step 04: Profile Page and Step 05: Backend Connection — the profile layout and live, user-scoped query helpers in `database/queries.py`.

## Routes

No new routes.

Extend the existing logged-in `GET /profile` route to accept optional `start_date` and `end_date` query parameters, for example `/profile?start_date=2026-09-01&end_date=2026-09-30`.

## Database changes

No database changes.

The existing `expenses.user_id` and `expenses.date` columns support user-scoped filtering. Expense dates use `YYYY-MM-DD` text as specified in Step 01. Reuse the existing schema, connection settings, and seed data; no migration or new index is required.

## Templates

- Create: None.
- Modify: `templates/profile.html` — add a GET form above the spending results with labeled Start date and End date inputs, an Apply filter button, a Clear filter link, and Last Month, Last 3 Months, and Last 6 Months preset links. Retain valid submitted dates, display validation errors, describe the active range, and distinguish an empty filtered result from an account with no recorded expenses. Preserve account details, summary cards, the transaction table, and category breakdown layout for valid requests.

## Files to change

- `app.py` — validate query parameters after authentication, pass normalized optional bounds through the three profile presentation helpers, and provide filter state and validation errors to the template.
- `database/queries.py` — extend the spending helpers and their shared aggregation query with optional date bounds, preserving existing return shapes and all-time defaults.
- `templates/profile.html` — add filter controls, active-range text, accessible validation feedback, and filtered empty states.
- `static/css/profile.css` — style the filter form, errors, and range text using existing variables; support keyboard focus and narrow screens.
- `tests/test_profile.py` — cover filter requests, validation, rendered controls, authentication, and read-only behavior. Update the existing whole-page single-form assertion to allow the new GET form while retaining separately scoped logout form and CSRF assertions. Adapt query mocks to optional date arguments without weakening their error-propagation checks.
- `tests/test_backend_connection.py` — cover inclusive and one-sided ranges, consistent aggregation, ordering, limits, isolation, and unchanged no-filter behavior.

## Files to create

No new files.

## New dependencies

No new dependencies.

Use the existing Flask, SQLite, pytest, and Python standard-library date facilities. Native HTML date inputs and a normal GET submission are sufficient.

## Rules for implementation

- No SQLAlchemy or other ORM; use the project's existing database approach.
- Use parameterized SQL queries only, with `?` placeholders for user IDs, dates, and limits. Never interpolate supplied values into SQL.
- Hash passwords with Werkzeug when passwords are involved; this feature requires no password or authentication changes.
- Use CSS variables rather than hardcoded hex color values. Preserve the existing no-inline-styles convention.
- All application templates must extend `base.html`; retain the existing profile inheritance and stylesheet head block.
- Keep routes in `app.py`, with no blueprints. Keep SQL and connection management in `database/queries.py`; query helpers must remain independent of Flask request and session state. Continue using `get_db()` with `contextlib.closing`, preserving `sqlite3.Row` and foreign-key enforcement.
- Authenticate through the existing `g.user` guard before validating filters or querying spending. Obtain the user ID exclusively from the authenticated user, never from query parameters. Anonymous, invalid-session, and deleted-account requests continue to redirect to login.
- Use `start_date` and `end_date` as optional GET parameters. A missing or empty value means that bound is absent. With neither bound, retain Step 05's all-time behavior; with only a start, include that date and later dates; with only an end, include that date and earlier dates. With both, include both boundary dates. Equal dates select one day. Future dates are allowed because stored expenses may be future-dated.
- Require every nonempty bound to be exactly a real calendar date in `YYYY-MM-DD` format. Reject malformed values, timestamps, non-zero-padded dates, surrounding whitespace, impossible dates, and a start date later than the end date. Validate on the server even when browser validation is bypassed; do not reuse the permissive stored-date presentation parser for request validation.
- Invalid filters return HTTP 400 using `profile.html` with a clear error, account details, the filter form, and Clear filter control. Omit spending results and skip all three spending queries on this response; do not silently fall back to all-time results or present zero totals as a successful filter. Preserve valid date values for correction; malformed values may render as empty date inputs, with the affected field identified by its error. Keep all reflected values escaped.
- Extend helper interfaces compatibly: `get_summary_stats(user_id, start_date=None, end_date=None)`, `get_recent_transactions(user_id, limit=10, start_date=None, end_date=None)`, and `get_category_breakdown(user_id, start_date=None, end_date=None)`. Preserve the positional `limit` argument and its validation. Route callers supply validated ISO date strings or `None`; existing calls without dates keep their current behavior. Pass identical bounds to all three helpers and their shared aggregation logic.
- Filter by the expense's `date`, not its creation timestamp or the account's membership date. Apply user and date predicates in SQL before aggregation and before the transaction limit. Share predicate construction where practical so the three sections cannot drift; any SQL fragments must be fixed application-controlled text with separately bound values.
- Keep the latest-10 transaction limit and `date DESC, id DESC` order. Totals, transaction count, top category, and category shares must use every matching expense, including matches beyond the displayed ten. Preserve Decimal cent rounding, alphabetical category tie-breaking, and existing percentage rounding: shares sum to 100 for a nonzero total, and remain zero when total spending is zero.
- A valid range with no matches returns HTTP 200 with `₹0.00`, zero transactions, top category `—`, no transaction rows, and an empty category breakdown. Show “No expenses in this date range.” and “No category spending in this date range.” For an unfiltered empty account, retain the existing empty-state wording.
- Use `<input type="date">` with associated labels, names, and retained valid values. Both inputs are optional. Explain that either date may be left blank, show the active range above all spending sections, and make clear that the transaction table shows at most ten matching expenses. Use an accessible error message and associate field errors with their inputs. The form and Clear filter link must work without JavaScript.
- Use `url_for('profile')` for the GET action and Clear filter link, and `url_for()` for all new or touched internal links. Clear filter navigates to `/profile` without date parameters. Keep dates in the URL so refresh and direct links reproduce the range; do not persist filters in the session or database. GET filtering needs no CSRF token; preserve the separate POST logout form and its CSRF protection.
- Provide Last Month, Last 3 Months, and Last 6 Months links alongside the custom date controls and Clear filter. Each preset covers the preceding 1, 3, or 6 complete calendar months, excluding the current month, with inclusive boundaries. For example, on 2026-10-04 the ranges are 2026-09-01 through 2026-09-30, 2026-07-01 through 2026-09-30, and 2026-04-01 through 2026-09-30. Use the same `start_date` and `end_date` URL parameters and validation/query path as custom ranges; no JavaScript is required. Retain the resulting dates in the inputs, identify the matching preset with `aria-current="true"`, and mark none selected for all-time, unmatched custom, or invalid ranges. This addition reflects the user's request to retain these quick options.
- Preserve user details, INR formatting, escaping, and existing category CSS fallbacks. Do not implement expense CRUD stubs, pagination, exports, or schema changes in this step. Do not mask database failures as validation errors or empty results.
- Follow PEP 8, existing naming conventions, and the current Flask/SQLite stack. Any JavaScript must remain vanilla JS. Do not install packages, change `requirements.txt`, raise the Python minimum implicitly, or introduce secrets.
- Tests must patch `database.db.DB_PATH` to a temporary SQLite file before importing the app and initialize it for each test, including when the app module is cached. Set test-only session environment values before import, restore mutable configuration with `monkeypatch`, close connections, and preserve real login/logout CSRF checks. Never read or mutate the developer's database or `.env`.
- Follow the project subagent policy during implementation: use an exploration subagent before implementation and a separate subagent to verify test results afterward. Step 05's all-time expectations remain valid for unfiltered requests; report any additional conflicts instead of silently weakening existing tests.

## Definition of done

- [ ] An authenticated `GET /profile` without date parameters returns HTTP 200 with blank optional date inputs and the existing all-time results. The unchanged demo seed still shows `₹235.50`, eight transactions, and Bills as the top category.
- [ ] Applying two valid dates places them in the URL, retains them in the form, and updates all three spending sections to the same inclusive range. Refreshing or opening that URL while signed in reproduces the results.
- [ ] Last Month, Last 3 Months, and Last 6 Months links select the preceding complete calendar months, including correct year rollover and leap-February boundaries. Each updates all spending sections, retains dates and selected state, and leaves stored data unchanged. Clear filter restores all-time results and removes selected preset state.
- [ ] Fixtures with expenses before, on, between, and after the boundaries prove that both boundary dates are included and outside dates are excluded. Equal bounds select only that day's expenses.
- [ ] Start-only, end-only, omitted, and empty bounds behave as specified; a valid leap day and a future range are accepted.
- [ ] Malformed dates, invalid leap days, impossible dates, timestamps, non-zero-padded dates, surrounding whitespace, and reversed ranges return HTTP 400 with visible validation feedback, no spending results, and no calls to spending query helpers.
- [ ] A range containing more than ten expenses shows only the newest ten, resolving equal dates by descending ID, while its summary and category totals include all matching expenses. Existing positional and keyword limit calls still work.
- [ ] Filtered totals, transaction count, top category, category order, cent rounding, and percentage shares match known fixture values. Ties retain alphabetical category ordering, nonzero totals yield shares summing to 100, and zero totals yield zero shares.
- [ ] A valid range with no matches returns HTTP 200 with zero summary values, top category `—`, and the specified filtered empty messages. Clearing the filter restores all-time results and existing unfiltered empty states.
- [ ] Two users with expenses on the same dates see only their own data, even when another user ID is supplied in the URL. Account name, email, and membership date do not change with the selected period.
- [ ] Anonymous and invalid or stale sessions redirect to login even when date parameters are malformed. Applying, clearing, refreshing, or submitting invalid filters leaves stored users and expenses unchanged.
- [ ] The filter works without JavaScript; labels, keyboard navigation, focus states, and validation messages are usable. At 375px and desktop widths, controls remain visible without introducing page-level horizontal overflow, and the existing table scroll behavior remains available.
- [ ] The GET filter form and POST logout form are separate, reflected input remains escaped, and logout still enforces its CSRF token. Simulated database failures remain distinguishable from an empty filtered result.
- [ ] `python -m pytest tests/test_profile.py tests/test_backend_connection.py` and the full `python -m pytest` suite pass using temporary databases without accessing the developer's local database.
