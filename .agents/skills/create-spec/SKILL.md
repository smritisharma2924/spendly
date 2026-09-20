---
name: create-spec
description: Create a specification file for the next expense-tracker feature. Use when the user wants to plan or specify a new feature before implementation.
---

You are a senior developer planning a new feature for the expense tracker.

Always follow the project-wide rules and conventions in `AGENTS.md`.

The user should provide:

- A step number
- A feature name

Example invocation:

`$create-spec step=2 feature="Registration"`

## Step 1 - Check working directory is clean
Run `git status` and check for uncommitted, unstaged, or untracked files. If any exist, stop immediately and tell the user to commit or stash changes before proceeding.
DO NOT CONTINUE until the working directory is clean.

## Step 2 — Parse the inputs
From the user's request, extract:

1. `step_number`
   - Must be an integer.
   - Zero-pad it to 2 digits for filenames.
   - Examples:
     - `2` → `02`
     - `11` → `11`

2. `feature_title`
   - Convert the requested feature name into a human-readable title in Title Case.
   - Examples:
     - `registration` → `Registration`
     - `login and logout` → `Login and Logout`

3. `feature_slug`
   - Create a file-safe slug from the feature title.
   - Use lowercase kebab-case.
   - Only use `a-z`, `0-9`, and `-`.
   - Maximum 40 characters.
   - Examples:
     - `Registration` → `registration`
     - `Login and Logout` → `login-logout`

4. `branch_name`
   - Construct the branch name using the feature slug.
   - Format: `feature/<feature_slug>`
   - Examples:
     - `registration` → `feature/registration`
     - `login-logout` → `feature/login-logout`

If the step number or feature cannot be confidently inferred from the user's request, ask the user to clarify before proceeding.

## Step 3 — Check branch name is not taken
Run `git branch` to list existing branches.
If `branch_name` is already taken, append a number: `feature/registration-01`, `feature/registration-02`, etc.

## Step 4 - Switch to main and pull latest changes
Run:
```
git checkout main
git pull origin main
```

## Step 5 - Create and switch to the feature branch
Run:
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase

Before writing the specification, read:

- `AGENTS.md` — project roadmap, conventions, architecture, and project-wide instructions
- `app.py` — existing routes and application structure
- `database/db.py` — existing database schema, helpers, and functions
- All existing Markdown specification files in `specs/` — avoid duplicating existing specifications and understand previous project decisions

Check `AGENTS.md` and the existing specifications to determine whether the requested step or feature is already marked complete or has already been specified.

If the requested step is already complete, warn the user and stop.

If a specification already exists for the same step or feature, do not overwrite or duplicate it. Tell the user which existing specification conflicts with the request and stop.

## Step 7 — Write the specification

Generate a specification document using exactly this structure:

---

# Spec: <feature_title>

## Overview

Write one paragraph describing what this feature does and why it exists at this stage of the expense-tracker roadmap.

## Depends on

List the previous steps or features that must be complete before this feature can be implemented.

If there are no dependencies, state that explicitly.

## Routes

List every new route required using this format:

- `METHOD /path` — description — access level (`public` or `logged-in`)

Only include routes that are actually required by this feature and that do not already exist.

If no new routes are required, state:

`No new routes.`

## Database changes

Describe every new table, column, constraint, index, or other database change required.

Always verify this section against `database/db.py` before writing it.

Do not propose database changes that already exist.

If none are required, state:

`No database changes.`

## Templates

List template changes under these categories:

- Create: list every new template and its path.
- Modify: list every existing template that must change and describe what changes.

If no template changes are required, state that explicitly.

## Files to change

List every existing project file that will need to be modified to implement the feature.

For each file, briefly state why it needs to change.

## Files to create

List every new file that will need to be created to implement the feature.

For each file, briefly state its purpose.

If no new files are required, state:

`No new files.`

## New dependencies

List any new Python/pip packages required by the feature.

Only add a dependency when the existing project cannot reasonably implement the feature without it.

If none are required, state:

`No new dependencies.`

## Rules for implementation

List the implementation constraints that must be followed.

Always include these project rules unless `AGENTS.md` explicitly says otherwise:

- No SQLAlchemy or other ORM; use the project's existing database approach.
- Use parameterized SQL queries only.
- Hash passwords with Werkzeug when passwords are involved.
- Use CSS variables rather than hardcoded hex color values.
- All application templates must extend `base.html`.

Also include any additional feature-specific constraints discovered from `AGENTS.md`, `app.py`, `database/db.py`, and existing specifications.

## Definition of done

Create a specific, testable checklist for the feature.

Every checklist item must describe something that can be verified by running or using the application.

Do not use vague items such as "works correctly" or "looks good."

---

## Step 8 — Save the specification

Save the completed specification to:

`specs/<step_number>-<feature_slug>.md`

Examples:

- `specs/02-registration.md`
- `specs/03-login-logout.md`

Do not modify an existing specification unless the user explicitly asks you to update it.

Do not implement the feature as part of this skill.

This skill is for research and specification creation only.

## Step 9 — Report to the user

After successfully creating the file, report:

`Spec file: specs/<step_number>-<feature_slug>.md`
`Title: <feature_title>`

Then tell the user to review the specification before beginning implementation.

Do not print the full specification in chat unless the user explicitly asks to see it.