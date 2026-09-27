---
name: test-feature
description: Write and run pytest tests for one Spendly feature spec by coordinating test-writer and spendly-test-runner in sequence. Use when the user requests the Spendly feature testing pipeline.
---

# Test Feature

Test one implemented Spendly feature against its spec. The custom writer writes
tests first; the separate custom runner executes only the selected feature tests.
This skill explicitly requests these two subagent delegations in sequence.

## Input and prerequisites

Read one spec name from the user's request, for example:

```text
$test-feature 05-backend-routes-for-profile-page
```

Accept a filename stem or a filename ending in `.md`; remove that extension before
resolving `specs/<spec-name>.md` relative to the project root. The stem may contain
letters, digits, hyphens, or underscores, but no path separators or shell syntax.
If missing or ambiguous, request a single spec name. If the file is absent, report
the exact missing path and list plausible existing specs without silently choosing
a different feature. Do not execute the pipeline until the input is resolved.

Read the spec, accepted user clarifications, and applicable `AGENTS.md`. Treat
the spec as the source of expected behavior. Do not implement missing features as
part of this pipeline or treat stale roadmap descriptions as proof of a failure.

Read and parse these custom-agent configurations:

| Role | Configuration | Declared agent name |
| --- | --- | --- |
| Writer | `.codex/agents/spendly-test-writer.toml` | `test-writer` |
| Runner | `.codex/agents/spendly-test-runner.toml` | `spendly-test-runner` |

Use the TOML `name` field to identify an agent, not its filename. Confirm the
configurations are valid and these custom roles can actually be invoked through
the available delegation capability. A file on disk alone does not establish
availability. If a required configuration or capability is missing, report the
blocker; do not silently substitute a generic agent or claim a delegation occurred.

## Select feature test files

- Prefer feature test paths explicitly named by the spec, such as
  `tests/test_backend_connection.py` for
  `specs/05-backend-routes-for-profile-page.md`.
- Include existing files that exercise other criteria of the same feature; for
  example, `tests/test_profile.py` covers route behavior for that backend spec.
  Check their assertions against the spec and accepted clarifications before
  counting them as coverage. Existing tests may encode a different expectation.
- If the spec does not name a path, reuse an existing test file for that feature.
  Otherwise create `tests/test_<feature_slug>.py`, removing a leading numeric step
  prefix and replacing hyphens with underscores.
- A feature may require more than one test file. Select only files needed for its
  requirements; do not include the full suite merely because a spec's definition
  of done mentions it. Report that broader check as outside this pipeline's scope.
- State the selected test paths before delegation and pass the same explicit list
  to both agents. Permit necessary fixtures under `tests/`, preserving existing
  tests and unrelated user changes. Do not create a duplicate test file just to
  match the spec filename.

## Step 1: Write tests

Invoke the custom writer with:

- The resolved spec path, accepted clarifications, selected test files, and
  applicable project instructions.
- An explicit statement that this is the `test-feature` workflow: write tests
  only; do not execute pytest, including collection-only or full-suite runs.
- A requirement to map spec criteria to inputs and expected outcomes before
  inspecting implementation. Source may then inform interfaces and fixture setup,
  but must not supply expected results. Cover happy paths, boundary cases,
  authentication, validation, and persistence where the spec requires them.
- Permission to create or extend only the selected feature tests and necessary
  fixtures under `tests/`. Reuse adequate existing coverage; do not overwrite
  existing tests or invent requirements. Report ambiguities and untestable criteria.
- Spendly's isolation requirements: patch `database.db.DB_PATH` to temporary
  SQLite storage before importing `app`, supply test-only configuration, restore
  mutable state, and preserve real CSRF checks. Do not access the developer's
  database or `.env`.
- A required handoff listing files changed, tests added or reused, each test's spec
  requirement, fixture changes, uncovered criteria, and blockers.

Wait until the writer completes. Inspect the reported files and changes to verify
the handoff; a pre-existing file alone is not evidence of completed work. A
documented no-change result is valid when existing tests already cover the spec.
Do not run pytest in this step. If a blocker or unresolved ambiguity prevents a
reliable handoff, report it and do not start the runner.

## Step 2: Run feature tests

Only after the writer's handoff is verified, invoke the custom runner with the same
spec and selected test paths, the test-to-spec mapping, and fixture notes.

Require the runner to:

- Verify the files exist, fixtures isolate database access before application
  import, and the existing project interpreter has pytest available. A virtual
  environment need not be activated when its interpreter is invoked directly.
- Run only the selected feature files from the project root. Prefer the existing
  `venv/bin/python`; otherwise use the configured project Python interpreter.
  For the example feature, the command is:

  ```bash
  venv/bin/python -m pytest tests/test_backend_connection.py tests/test_profile.py -v -ra
  ```

  Pass multiple selected files as separate quoted arguments where needed.
  Do not run the full suite, install packages, or start the development server.
- Wait for execution to finish and report the exact command, interpreter, exit
  code, and observed pytest counts, including skips, xfails, and xpasses.
  Treat collection errors, interruption, and zero collected tests explicitly.
- Analyze failures against the spec and tests, consulting relevant application
  source only for diagnosis. Distinguish implementation bugs, missing features,
  test defects, ambiguous requirements, and environment problems. Separate
  observed evidence from root cause hypotheses.
- Make no code or test edits. If a focused rerun is needed to investigate
  ambiguous output, stay within the selected files and record every command and
  outcome; do not hide an initial failure behind a passing retry.
- Check coverage against the supplied criteria and report missing assertions or
  browser-only requirements. Do not infer full feature correctness or architecture
  compliance from passing tests alone.

Wait for the runner to complete before reporting results. If either agent is
blocked, report completed work and the blocker without claiming unexecuted work
succeeded. Fixing application code or repairing tests after execution is outside
this pipeline; report the issue for a separate follow-up.

## Final report

Return a concise Testing Pipeline Report for the spec:

1. **Tests written:** spec and test paths; files changed; tests added or reused with
   a one-line mapping to spec criteria; fixture changes and coverage gaps.
2. **Execution:** exact commands, interpreter, exit codes, observed counts, and
   pass rate with an explicit denominator (N/A when no tests ran). Include
   failure evidence, classifications, hypotheses, and relevant warnings.
3. **Verdict:** one of:
   - **Selected feature tests passed** — execution completed successfully and no
     failures, errors, or unresolved coverage gaps remain within the selected scope.
   - **Needs attention** — failures, skipped or xfailed requirements, inconsistent
     reruns, ambiguous expectations, or other coverage gaps remain.
   - **Blocked — testing incomplete** — required delegation or execution could not
     complete, or no tests were collected.

Always state that the full regression suite was not run. A scoped passing result
is not a declaration that the whole application or every spec criterion is ready
for code review.
