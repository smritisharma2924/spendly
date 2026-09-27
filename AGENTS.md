# AGENTS.md

## Project overview

Spendly is a personal expense tracker built with Flask and SQLite. It includes styled public pages, registration, session-based login and logout, a database-backed profile dashboard, and a JavaScript video modal. Expense add, edit, and delete routes remain unimplemented stubs.

---

## Architecture

```
expense-tracker/
├── app.py              # Flask app and all routes; no blueprints
├── database/
│   ├── __init__.py
│   ├── db.py           # Connections, schema, seeds, and authentication queries
│   └── queries.py      # Read-only profile queries
├── templates/
│   ├── base.html       # Shared layout
│   └── *.html          # Landing, auth, profile, terms, and privacy pages
├── static/
│   ├── css/
│   │   ├── style.css   # Primary stylesheet
│   │   └── profile.css # Profile page styles
│   └── js/
│       └── main.js     # Vanilla-JS video modal
├── tests/             # Registration, authentication, profile, and query tests
├── specs/             # Feature requirements and acceptance criteria
└── requirements.txt
```

**Where things belong:**

- New routes → `app.py` only, no blueprints
- Database connections, schema, seeds, and authentication queries → `database/db.py`
- Profile queries → `database/queries.py`; keep all database logic in `database/`, using the module specified by the feature spec, not inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → `static/css/`, linked through `base.html`'s `head` block
- Tests → `tests/test_*.py`; existing fixtures are local to each test module

---

## Code style

- Python: four-space indentation, PEP 8, and `snake_case` variables and functions
- Templates: page templates extend `base.html`; use `url_for()` for internal links and form actions
- Routes: keep handlers thin—validate input, call database helpers, then render or redirect
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- JavaScript: use vanilla JS, camelCase names, and `const`/`let`
- Error handling: use `abort()` for HTTP errors and templates for user-facing validation; raw strings are only acceptable for current stubs

---

## Tech constraints

- **Flask 3.1.3 and Werkzeug 3.1.6** — no FastAPI, Django, or other web frameworks
- **SQLite only** — persistence is implemented; no PostgreSQL, SQLAlchemy, or external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — use `requirements.txt` as-is unless explicitly instructed, and synchronize it when dependencies change
- No Python version is declared; avoid introducing syntax that silently raises the minimum version

---

## Subagent Policy

- Before implementing a feature, use an exploration subagent for codebase research
- After implementation, use a separate subagent to verify test results
- Before presenting a plan, delegate codebase research to an exploration subagent
- In Plan mode, use a planning subagent

---

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
python -m pip install -r requirements.txt

# Configure a nonempty SECRET_KEY in the environment before startup.
# For a local shell session, generate one with:
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Run dev server (port 5001; SESSION_COOKIE_SECURE defaults to false for local HTTP)
python app.py

# Run all tests
python -m pytest

# Run a specific test file
python -m pytest tests/test_auth.py

# Run a specific test by name
python -m pytest -k "test_name"

# Run tests with output visible
python -m pytest -s
```

There is no build or lint command. Pytest and pytest-flask are pinned in `requirements.txt`. Tests exist in `tests/test_registration.py`, `tests/test_auth.py`, `tests/test_profile.py`, and `tests/test_backend_connection.py`; no coverage target is configured. The commands above assume the virtual environment is active; otherwise use `venv/bin/python` directly. The `export` example is for POSIX shells. The app does not load `.env` automatically.

## Test isolation

- Importing `app.py` initializes and seeds the database. Patch `database.db.DB_PATH` to a temporary SQLite file before importing the app; setting `app.config["DATABASE"]` does not redirect database access.
- Set test-only `SECRET_KEY` and `SESSION_COOKIE_SECURE` environment values before import. Initialize the temporary database for each test even when the app module is cached, and restore mutable app configuration with `monkeypatch`.
- Do not read or mutate the developer's database or `.env`. Close test connections.
- Login and logout use custom session-bound CSRF tokens. Keep these checks enabled, obtain real tokens for successful form submissions, and account for token rotation at login. `WTF_CSRF_ENABLED` is not a Spendly setting. Registration currently has no CSRF check.

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /terms` | Implemented — renders `terms.html` |
| `GET /privacy` | Implemented — renders `privacy.html` |
| `GET, POST /register` | Implemented — validation, hashed passwords, duplicate-email handling, redirect to login |
| `GET, POST /login` | Implemented — credentials, CSRF checks on POST, sessions, redirect to profile when authenticated |
| `POST /logout` | Implemented — CSRF validation and session clearing; GET/HEAD return 405 |
| `GET /profile` | Implemented — authenticated account details, spending totals, latest transactions, category breakdown |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<int:id>/edit` | Stub — Step 8 |
| `GET /expenses/<int:id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

Feature specs describe incremental steps. Step 05 supersedes Step 04's static profile data. The current login destination is `/profile`, as recorded in the updated Step 03 spec. If a requirement conflicts with another spec or current tests, report the conflict instead of silently changing assertions or reverting completed features.

---

## Warnings and things to avoid

- Replace a completed stub's raw string with the appropriate template, redirect, or HTTP error
- Use `url_for()` for new links and replace hardcoded internal paths when touching a template
- **Never put DB logic in route functions** — it belongs in `database/`, using `db.py` or `queries.py` according to the feature spec
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- `database/db.py` contains implemented connection, schema, seed, and user helpers; inspect their actual interfaces before using them
- `get_db()` returns a fresh connection using `sqlite3.Row` with `PRAGMA foreign_keys = ON`. Callers must close it, normally with `contextlib.closing`; preserve these guarantees
- When implementing deletion, use a state-changing method such as POST rather than GET
- Session identity is the integer `user_id`; `load_current_user()` resolves it to `g.user` and clears invalid or stale identities
- The schema and stored expenses exist, but expense CRUD routes are still stubs
- Read secrets such as `SECRET_KEY` from environment variables; never hardcode them
- Do not commit ignored local files: `.env`, `expense_tracker.db`, `venv/`, bytecode, `.DS_Store`, or `.claude/plans/`
- The development server runs in debug mode on **port 5001**; do not use debug mode in production

## Commit and pull request guidelines

Follow the repository's concise, lowercase, scoped commit style, for example `landing: add privacy policy page and route`. Keep commits focused. Pull requests should summarize behavior changes, list tests or manual checks, link relevant issues, and include screenshots for visible UI changes.
