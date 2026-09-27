---
name: code-review-feature
description: Review a completed Spendly feature against its spec by running the security and quality reviewers in parallel, then combine their findings into one report. Use when the user requests the Spendly feature code review and supplies a spec name.
---

# Code Review Feature

Review the feature named in the user's request. Example invocation:

```text
$code-review-feature 03-login-logout
```

Accept one spec filename stem, optionally ending in `.md`; remove that extension before resolving `specs/<spec-name>.md`. The stem may contain letters, digits, hyphens, or underscores, but no path separators or shell syntax. Request a valid name if necessary. Substitute the actual name in paths and messages.

Default to uncommitted feature changes. For committed work, accept an explicitly supplied comparison base and target, for example: `$code-review-feature 05-backend-routes-for-profile-page; review committed changes from 244c760 to c1aa9e1`. These are instructions in the user's message, not a shell command. Do not infer a comparison range from recent history.

If no name is provided, stop immediately and say:

> Please provide a spec name. Usage: $code-review-feature <spec-name> e.g. $code-review-feature 03-login-logout

## Pre-flight check

Work from the Spendly project root. Confirm that `specs/<spec-name>.md` exists. If it is missing, stop and report the exact missing path and list plausible existing specs without silently choosing one.

Read and parse `.codex/agents/spendly-security-reviewer.toml` and `.codex/agents/spendly-quality-reviewer.toml`. Confirm that their declared `name` fields are `spendly-security-reviewer` and `spendly-quality-reviewer`, respectively, and that both custom roles are callable through the available delegation tool. A file on disk alone does not establish availability. If a configuration is missing or invalid, or a role cannot be invoked, stop and report the blocker without silently substituting a generic agent.

Read the spec, accepted user clarifications, and applicable `AGENTS.md`. Respect explicit superseding requirements: Step 05 replaces Step 04's static profile data, and the amended Step 03 login destination is `/profile`. Report unresolved requirement conflicts instead of inventing an expectation.

### Select the comparison

For **uncommitted changes**, collect both diff views without changing Git state:

```bash
git diff --
git diff --staged --
```

Keep the unstaged and staged results labeled separately, then pass both together as the review input. They are two views of the current changes and should not be concatenated into a misleading single patch. Use `git status --short` to identify relevant untracked feature files, since `git diff` does not show them; include their contents as clearly labeled new-file review input. Do not stage them.

Review the final working-tree content, using the two patches to identify changes. Do not report an intermediate staged issue that an unstaged edit already fixes. State that staged-only content has not been separately approved.

For **committed changes**, require both a base and target revision. Resolve each to a commit with `git rev-parse --verify --end-of-options '<revision>^{commit}'`, passing the revision as one safely quoted argument, never interpolating raw user text into shell code. If a revision is missing or invalid, request it before proceeding. Record the resolved commit IDs and use `git diff <base-id> <target-id> --` to compare those exact snapshots. For a single commit, the user must identify its parent/base as well; do not choose a merge parent or merge-base silently.

Read changed files and surrounding source from the target commit, for example using `git show <target-id>:<path>`, rather than using potentially different working-tree content. Use target-snapshot line numbers in findings. Keep the current resolved spec and accepted clarifications as the stated review requirements; disclose that choice when reviewing a historical snapshot. Do not check out revisions or include staged, unstaged, or untracked changes in a committed comparison.

For removed code, consult the base snapshot and label any base-side references explicitly. Pass file paths as safely quoted arguments as well.

Identify which changes belong to this feature and give both reviewers the same scope. Exclude unrelated changes and name those exclusions in the report. If feature scope is ambiguous, request clarification rather than selecting an arbitrary subset.

In uncommitted mode, if no relevant changes remain after scope filtering, say:

> No uncommitted feature changes found. To review committed work, provide a comparison base and target.

For an empty committed comparison, report that no feature changes exist between the selected revisions. In either case, stop without issuing an approval verdict.

### Map requirements

Before delegation, map the applicable acceptance criteria to the selected changes and relevant surrounding code or existing tests. Give both reviewers this map and ask them to assess criteria within their specialty. The coordinator remains responsible for functional requirements outside those specialties, including missing implementation that produces no diff hunk. Distinguish evidence supporting a criterion, a confirmed unmet criterion, an unresolved requirement conflict, and behavior not verified by static inspection. Do not treat a test's existence as proof it passed. Do not expand into unrelated features or flag out-of-scope expense stubs as completed functionality.

## Step 1: Parallel review

Start **spendly-security-reviewer** and **spendly-quality-reviewer** in the same review phase, without waiting for one to finish before starting the other. This skill explicitly requests those two subagent delegations. Give both the same labeled review input, comparison mode and revisions where applicable, feature name, spec path, accepted clarifications, requirements map, and applicable project instructions. If the two agents cannot be launched in parallel, report that limitation; do not claim that a parallel review occurred.

Give **spendly-security-reviewer** this task:

- Spec and acceptance criteria: `specs/<spec-name>.md`, with the shared requirements map.
- Review input: the selected feature comparison and snapshot, with labels and scope exclusions.
- Source to consult for context: `app.py` and `database/`, plus any directly relevant surrounding code needed to verify a finding.
- Review only changed code for security vulnerabilities. Do not comment on quality or style. Return the agent's structured Security Review with verified file and line references and concrete recommendations. Do not edit files.

Give **spendly-quality-reviewer** this task:

- Spec and acceptance criteria: `specs/<spec-name>.md`, with the shared requirements map.
- Review input: the same feature changes supplied to the security reviewer.
- Source to consult for context: `app.py`, `database/`, and `templates/`, plus any directly relevant surrounding code needed to verify a finding.
- Review only changed code for quality, Flask practices, and maintainability. Do not comment on security. Return the agent's structured Quality Review with verified file and line references and concrete recommendations. Do not edit files.

Wait until both agents finish. If either fails or returns no usable output, report the failure and do not present the other review as a complete combined review.

## Step 2: Unified report

Combine both completed reviews into one report. De-duplicate overlapping observations; if the same changed line raises different security and quality concerns, use one action item that identifies both perspectives while retaining the distinct reasons. Preserve each reviewer's positive observations. Distinguish confirmed issues from possibilities and avoid claiming severity unsupported by the reviewed code.

Reconcile the requirements map with both reviews before choosing a verdict. Include confirmed missing requirements as coordinator findings even when neither specialist reports a code issue. Name unresolved conflicts and verification gaps; never convert them into an unsupported claim of feature completion.

Use this structure:

```text
Code Review Report — <spec-name>

Review Scope
[Spec, comparison mode, revisions or working-tree snapshot, files, and exclusions]

Requirements Coverage
[Criteria, supporting evidence, unmet requirements, conflicts, and unverified behavior]

Security Findings
[Security review findings, learning notes, and safe patterns]

Quality Findings
[Quality review findings, polish ideas, and good patterns]

Combined Action Plan
[Ordered, concrete checklist with file/line, proposed change, and reason]

Overall Verdict
[APPROVED / APPROVED WITH SUGGESTIONS / CHANGES REQUESTED / INCOMPLETE]
```

Order actionable items as follows where those categories are supported by the findings:

1. Critical or high security findings.
2. Quality findings that materially impair correct behavior or maintainability.
3. Medium or low security findings.
4. Optional quality polish.

The reviewers are educational and do not assign blocking labels themselves. As the coordinator, use the actual impact of the findings to choose and explain one verdict:

- **APPROVED — within the stated review scope**: no actionable issues, confirmed unmet requirements, or unresolved requirement conflicts found.
- **APPROVED WITH SUGGESTIONS**: only optional improvements remain within the stated scope.
- **CHANGES REQUESTED**: a confirmed issue or unmet requirement has enough impact to warrant a fix now. Name the issue and reason; do not use this verdict for style nits or speculative risks.
- **INCOMPLETE**: unresolved scope, requirement conflicts, or missing evidence prevent a reliable review conclusion. Explain what remains needed. If confirmed issues also exist, preserve them in the report.

Approval is a static review conclusion, not proof that tests passed or that the feature is ready to ship. List runtime and browser behavior not verified by this review, along with any supplied test results and their scope. Do not run tests or application code as part of this review. Do not claim the entire application is secure or fully reviewed. If either reviewer could not complete, provide a blocked status with the available evidence instead of an approval verdict.

## Step 3: Ask about fixes

After presenting the complete report and a concrete action plan, ask:

> Do you want me to implement the action plan now?

Wait for the user's answer before implementing fixes. The review request authorizes inspection and reporting; the action plan is a separate follow-up change. If the user has already authorized implementing review fixes in this conversation, use that authorization and proceed without asking again. A later approved fix request should address only the agreed actions and verify the affected behavior.

## Rules

- Do not edit project files during pre-flight, review, or report preparation.
- Launch both reviewers in parallel on the same feature scope.
- Always run the pre-flight diff check and verify the spec exists.
- Keep specialist findings tied to changed code for the specified feature; use surrounding code for context. The coordinator also reports missing requirements within that feature's agreed scope.
- Do not present a partial review as complete if either reviewer fails or returns no usable output.
