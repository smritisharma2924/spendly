# Spec: Login and Logout

## Overview

Allow registered users to sign in with their email and password, remain signed in across requests through a Flask session, and sign out through the shared navigation. Step 03 builds on the existing SQLite database and registration handler. Successful sign-in returns to the landing page, which displays the signed-in user's name and a logout control; profile and expense features remain separate roadmap steps.

## Depends on

- Step 01: Database Setup (`specs/01-database-setup.md`), including the users table, hashed demo password, and `get_db()`, `init_db()`, and `seed_db()` helpers.
- Step 02: Registration (`specs/02-registration.md`), including `create_user()`, normalized email addresses, Werkzeug password hashes, and registration tests.
- The existing login template and shared layout. Database setup and registration are implemented in the current code despite the older descriptions in `AGENTS.md`; login POST handling and logout are not implemented.

## Routes

- `POST /login` — validate credentials and establish a session, then redirect to the landing page — access level (`public`).
- `POST /logout` — validate the logout form, clear the session, and redirect to the login page; also safely accept a valid anonymous form submission — access level (`public`).

Add POST support to the existing `/login` handler and replace the existing GET-only `/logout` stub with POST-only behavior. No additional URL paths are required. Existing `GET /login` renders the form for anonymous visitors and redirects signed-in visitors to the landing page. `GET /logout` and `HEAD /logout` return HTTP 405 without changing the session.

## Database changes

No database changes.

The existing users table already contains `id`, `name`, unique `email`, `password_hash`, and `created_at`. Add read helpers in `database/db.py` for finding a user by email and by ID. Reuse the current schema and seed data; sessions use Flask's signed cookie and require no session table.

## Templates

- Create: None.
- Modify: `templates/login.html` — use `url_for('login')` for the form action, add a hidden CSRF token, retain the submitted email after errors, keep the password empty, and display validation errors through the existing error block. Set appropriate email and current-password autocomplete attributes. Do not impose registration's eight-character minimum on login.
- Modify: `templates/base.html` — show Sign in and Get started to anonymous visitors; show the escaped current user's name and a POST logout form with a hidden CSRF token to signed-in visitors. Convert the existing terms and privacy links to `url_for()`. Preserve the shared layout and make the logout button usable on desktop and mobile.

## Files to change

- `app.py` — configure the session secret and cookie settings, add CSRF token generation and validation, load the current user for each request, implement login and logout, and supply authentication state to templates.
- `database/db.py` — add user lookup helpers with the existing connection lifecycle and registration-compatible email matching.
- `templates/login.html` — update the form action, token, autocomplete attributes, and retained email value.
- `templates/base.html` — add navigation that reflects the current user and a logout form; update touched internal links.
- `static/css/style.css` — style the navigation form and button using existing CSS variables, with a visible keyboard focus state and mobile access.
- `tests/test_registration.py` — configure a test-only session secret before application import and update login-page cookie assertions to permit an anonymous CSRF session while continuing to assert that registration never authenticates the user.

## Files to create

- `tests/test_auth.py` — cover login, logout, user lookup, sessions, CSRF validation, navigation, and configuration using Flask's test client and temporary SQLite databases.

## New dependencies

No new dependencies.

Use Flask sessions, Werkzeug password verification, existing pytest packages, and Python standard-library facilities such as `os`, `secrets`, and `hmac`.

## Rules for implementation

- No SQLAlchemy or other ORM; use the project's existing SQLite database approach.
- Use parameterized SQL queries only, with `?` placeholders for supplied values.
- Hash passwords with Werkzeug when passwords are created; verify existing hashes with `check_password_hash()` during login. Never compare newly generated hashes, store plaintext passwords, or log submitted credentials.
- Use CSS variables rather than hardcoded hex color values.
- All application templates must extend `base.html`; the shared base remains the root layout.
- Keep routes in `app.py`, with no blueprints. Keep handlers thin and all SQL and connection management in `database/db.py`. Close connections using the existing `contextlib.closing` pattern and preserve `sqlite3.Row` and foreign-key enforcement.
- Read `SECRET_KEY` from the environment before serving requests. Missing or empty configuration must stop startup with a clear configuration error. Do not provide a hardcoded fallback or generate a different secret on every startup. Tests must supply their own test-only secret before importing the app.
- Use Flask's signed session cookie, with `HttpOnly` enabled and `SameSite=Lax`. Support enabling `Secure` through environment configuration for HTTPS deployment while allowing the local HTTP development server on port 5001. Do not enable production debug mode.
- Store only the integer `user_id` as authenticated identity in the session, alongside the CSRF token. Do not store a password, password hash, email, or name in the cookie. Use a non-permanent session; remember-me functionality is outside this step.
- Load the current user by ID for each request and expose it as `g.user` for the shared layout. An invalid ID type or a deleted user clears stale session state and is treated as anonymous without an application error. Anonymous requests must not require a user lookup.
- Generate an unpredictable session-bound CSRF token for the login and logout forms. Validate both POST handlers with a constant-time comparison before applying authentication changes. Missing or invalid tokens return HTTP 400 and must not sign in or log out a user. Use the login template for login errors and `abort(400)` for invalid logout requests. Adding CSRF to registration is outside this step.
- Read missing fields safely. Trim and lowercase the email using the same Python normalization as registration. Require exactly one `@`, nonempty local and domain parts, and no whitespace after trimming. Do not add domain restrictions that would reject an account accepted by registration.
- Match existing mixed-case emails, including non-ASCII letters, consistently with registration's Python `lower()` behavior. Do not rely solely on SQLite's default `LOWER()` or `NOCASE` for Unicode matching. If legacy data contains multiple case-equivalent accounts, reject the ambiguous login with the generic credential error instead of choosing an account arbitrarily.
- Require a nonempty password, but do not trim, normalize, or apply the registration minimum length to it: the seeded demo password `demo123` must remain usable. Missing fields or malformed email return HTTP 400 with a clear form error; an unknown email or incorrect password returns HTTP 401 with the same message, “Invalid email or password.”
- Preserve the submitted email through normal escaped Jinja values on form errors. Never repopulate or expose the password, and never use the `safe` filter on user data.
- On successful login, clear previous session contents, set `user_id`, create a fresh CSRF token, and return HTTP 302 to `url_for('landing')`. Subsequent requests identify the same user. Failed anonymous login attempts never create authenticated state.
- A signed-in visitor to `/login` is redirected to the landing page; POST requests must still pass CSRF validation before this redirect and must not silently switch accounts. Use the fixed landing destination and ignore any submitted `next` URL.
- A valid logout POST clears the entire session and returns HTTP 302 to `url_for('login')`. It does not delete or modify users or expenses. A valid anonymous logout POST has the same redirect behavior; GET requests never log anyone out.
- Use `url_for()` for new or touched internal links, actions, and redirects. Follow PEP 8 and existing naming conventions. Any JavaScript must remain vanilla JS; these forms must work without JavaScript.
- Do not implement profile or expense stubs, password reset, registration auto-login, or additional authentication services in this step. Preserve the current registration behavior and schema.
- No new pip packages or changes to `requirements.txt` are needed. Do not introduce a higher Python version requirement or commit `.env`, the local database, bytecode, or virtual environments.
- Tests must redirect `database.db.DB_PATH` to a temporary database before importing `app.py`, because startup initializes and seeds SQLite. Configure and restore session settings explicitly so tests remain independent even when the app module is cached. Exercise startup configuration in isolation without touching the developer's database.
- Follow the project subagent policy during implementation: use an exploration subagent before implementation and a separate subagent to verify test results afterward.

## Definition of done

- [ ] Starting the app with a configured environment secret succeeds; starting it without a secret or with an empty secret reports a clear configuration error.
- [ ] Anonymous `GET /login` returns HTTP 200 with an email field, an empty password field, and a CSRF-protected POST form. Public pages display Sign in and Get started.
- [ ] The seeded `demo@spendly.com` / `demo123` credentials and an account created through registration can each sign in, returning HTTP 302 to `/`.
- [ ] Following successful login displays the user's escaped name and a working logout control in the shared navigation. The same client remains signed in on later requests, while a separate client remains anonymous.
- [ ] Surrounding whitespace and case variations in email authenticate the same account, including a preexisting mixed-case non-ASCII email. Ambiguous legacy email matches are rejected without authenticating either account.
- [ ] Missing or empty fields and malformed emails return HTTP 400 with a visible error when browser validation is bypassed. Unknown emails and incorrect passwords return HTTP 401 with identical credential-error text and no authenticated session.
- [ ] A password containing surrounding spaces only succeeds when supplied exactly. The seven-character seeded demo password is accepted without altering the existing registration password policy.
- [ ] Form errors retain escaped email text, leave the password input empty, and do not disclose the submitted password in the response.
- [ ] Login clears preexisting session values and rotates the CSRF token. The resulting cookie contains the user ID and token without password hashes or personal profile data, has HttpOnly and SameSite=Lax attributes, and gains Secure when HTTPS configuration is enabled.
- [ ] Missing, incorrect, or another client's CSRF token returns HTTP 400 for login and logout without changing authenticated identity. A pre-login token cannot be reused to log out after successful login.
- [ ] Signed-in GET and valid POST requests to `/login` redirect to `/` without changing users; a supplied external `next` URL never controls the redirect destination.
- [ ] A valid logout POST returns HTTP 302 to `/login`, clears authenticated session state, and restores anonymous navigation. A valid anonymous logout POST also redirects without error.
- [ ] `GET /logout` and `HEAD /logout` return HTTP 405 and preserve an active session. The navigation submits logout with POST and remains keyboard accessible and visible at mobile widths.
- [ ] A tampered session cookie, an invalid session user ID, and a session referencing a deleted user are treated as anonymous without an application error.
- [ ] Login and logout leave users, password hashes, expenses, and seed records unchanged. Registration still redirects to login without authenticating the new user.
- [ ] `python -m pytest tests/test_auth.py`, `python -m pytest tests/test_registration.py`, and the full `python -m pytest` suite pass using temporary databases, leaving the developer's local database unchanged.
