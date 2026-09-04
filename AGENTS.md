# AGENT.md

## Project overview

Spendly is an early-stage personal expense tracker built with Flask. It currently serves styled public pages, login and registration forms, and a JavaScript video modal. SQLite persistence, authentication, profiles, and expense management are planned but not implemented.

---

## Architecture

```
expense-tracker/
├── app.py              # Flask app and all routes; no blueprints
├── database/
│   ├── __init__.py
│   └── db.py           # Comment-only placeholder for SQLite helpers
├── templates/
│   ├── base.html       # Shared layout
│   └── *.html          # Landing, auth, terms, and privacy pages
├── static/
│   ├── css/
│   │   └── style.css   # Primary stylesheet
│   └── js/
│       └── main.js     # Vanilla-JS video modal
└── requirements.txt
```

**Where things belong:**

- New routes → `app.py` only, no blueprints
- Database connections, schema, seeds, and queries → `database/db.py`, not inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → `static/css/`, linked through `base.html`'s `head` block
- Tests → `tests/test_*.py`; no `tests/` directory exists yet

---

## Code style

- Python: four-space indentation, PEP 8, and `snake_case` variables and functions
- Templates: extend `base.html` and use `url_for()` for new or touched internal links; some current links and form actions remain hardcoded
- Routes: keep handlers thin—validate input, call database helpers, then render or redirect
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- JavaScript: use vanilla JS, camelCase names, and `const`/`let`
- Error handling: use `abort()` for HTTP errors and templates for user-facing validation; raw strings are only acceptable for current stubs

---

## Tech constraints

- **Flask 3.1.3 and Werkzeug 3.1.6** — no FastAPI, Django, or other web frameworks
- **SQLite only** — it is planned but not wired up; no PostgreSQL, SQLAlchemy, or external DB
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

# Run dev server (port 5001)
python app.py

# Run all tests
python -m pytest

# Run a specific test file
python -m pytest tests/test_routes.py  # Example future test file

# Run a specific test by name
python -m pytest -k "test_name"

# Run tests with output visible
python -m pytest -s
```

There is no build or lint command. Pytest and pytest-flask are pinned in `requirements.txt`, but no tests or coverage target are currently committed.

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET /terms` | Implemented — renders `terms.html` |
| `GET /privacy` | Implemented — renders `privacy.html` |
| `GET /register` | Page only — POST form handler is missing and returns 405 |
| `GET /login` | Page only — POST form handler is missing and returns 405 |
| `GET /logout` | Stub — Step 3 |
| `GET /profile` | Stub — Step 4 |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<int:id>/edit` | Stub — Step 8 |
| `GET /expenses/<int:id>/delete` | Stub — Step 9 |

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- Replace a completed stub's raw string with the appropriate template, redirect, or HTTP error
- Use `url_for()` for new links and replace hardcoded internal paths when touching a template
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **`database/db.py` contains comments only** — do not assume its helpers exist
- Future `get_db()` must use `sqlite3.Row` and enable `PRAGMA foreign_keys = ON` on every connection
- When implementing deletion, use a state-changing method such as POST rather than GET
- Authentication, sessions, the schema, and expense persistence do not exist yet
- Read future secrets such as `SECRET_KEY` from environment variables; never hardcode them
- Do not commit ignored local files: `.env`, `expense_tracker.db`, `venv/`, bytecode, `.DS_Store`, or `.claude/plans/`
- The development server runs in debug mode on **port 5001**; do not use debug mode in production

## Commit and pull request guidelines

Follow the repository's concise, lowercase, scoped commit style, for example `landing: add privacy policy page and route`. Keep commits focused. Pull requests should summarize behavior changes, list tests or manual checks, link relevant issues, and include screenshots for visible UI changes.
