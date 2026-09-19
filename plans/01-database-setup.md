# Database setup implementation plan

## Summary

Implement the SQLite foundation in `specs/01-database-setup.md`. Change only
`database/db.py` and startup initialization in `app.py`, preserving existing
routes and dependencies. This plan is the separately requested documentation
artifact; add no other source files.

## Database implementation

- Resolve module-level `DB_PATH` relative to `database/db.py`, pointing to the
  project-root `expense_tracker.db`, which Git already ignores.
- Implement `get_db()` with no arguments. Return a fresh SQLite connection with
  `sqlite3.Row` and foreign keys enabled. Callers own closing the connection.
- Implement `init_db()` with static `CREATE TABLE IF NOT EXISTS` statements:
  - `users`: autoincrement integer primary key; required text name, unique
    required text email, required text password_hash; text created_at defaulting
    to `(datetime('now'))`.
  - `expenses`: autoincrement integer primary key; required integer user_id
    referencing users.id; required REAL amount; required text category and date;
    nullable text description; text created_at with the same timestamp default.
- Commit successful initialization, roll back failures, and always close
  helper-owned connections. Let SQLite exceptions propagate for debugging.
- Bind all supplied SQL values with `?` placeholders. Add no extra schema
  constraints, indexes, or cascading deletion behavior.

## Seed data and startup

- Implement `seed_db()` assuming initialization has completed. Begin an immediate
  transaction before checking for any existing user; return without changes when
  one exists. This also prevents concurrent startup calls from both seeding.
- Otherwise insert Demo User, demo@spendly.com, and a Werkzeug-generated hash of
  demo123. Use the inserted user ID for every expense.
- Insert the following records using the current local year and month,
  ISO YYYY-MM-DD dates, and null descriptions:

| Day | Category | Amount |
| --- | --- | --- |
| 1 | Food | 12.50 |
| 4 | Transport | 20.00 |
| 8 | Bills | 75.00 |
| 12 | Health | 30.00 |
| 16 | Entertainment | 18.00 |
| 20 | Shopping | 45.00 |
| 24 | Other | 10.00 |
| 28 | Food | 25.00 |

- Commit the demo user and expenses together, roll back the entire seed on
  failure, and always close the connection.
- Import get_db, init_db, and seed_db in app.py. Immediately after constructing
  Flask, call initialization and then seeding inside app.app_context(), before
  route declarations and outside the __main__ guard.

## Validation

Use temporary databases and a temporary verification script, redirecting DB_PATH
before invoking helpers or importing the app. Do not add tracked test files.

- Check named-column access, foreign keys on each connection, exact schema,
  defaults, and preservation of existing data on repeated initialization.
- Verify one demo user, password hash verification, eight expenses covering all
  seven categories, and valid dates in the current month.
- Repeat initialization, seeding, and app startup; verify unchanged records.
  Verify that any existing non-demo user suppresses seeding.
- Confirm duplicate emails and orphan expenses raise integrity errors. Force a
  seed failure and confirm full rollback, followed by a successful retry.
- Verify app import initializes a fresh database, existing public pages succeed,
  and placeholder routes remain unchanged.
- Run available repository tests. Have a separate verification subagent review
  results as required by AGENTS.md, and inspect the final diff.

## Defaults and boundaries

Demo seeding runs unconditionally at startup as specified. No authentication,
expense route implementation, migrations, templates, or additional packages are
included. The runtime database remains ignored by Git.
