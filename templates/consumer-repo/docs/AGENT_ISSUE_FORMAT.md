# Agent Issue Format Guide

This document defines the canonical structure for issues that feed into the Codex keepalive automation pipeline. Follow this format when creating issues for automated agent processing.

## Quick Reference Template

```markdown
## Why

<!-- Brief explanation of the problem or opportunity -->

## Scope

<!-- What this issue covers and its boundaries -->

## Non-Goals

<!-- What is explicitly out of scope -->

## Tasks

- [ ] First task description
- [ ] Second task description
- [ ] Third task description

## Acceptance Criteria

- [ ] First verifiable criterion
- [ ] Second verifiable criterion

## Implementation Notes

<!-- Optional: Technical details, file paths, constraints -->
```

---

## Section Details

### Required Sections

| Section | Purpose | Aliases |
|---------|---------|---------|
| **Tasks** | Work items with checkboxes | `Task List`, `Implementation` |
| **Acceptance Criteria** | Verifiable completion conditions | `Acceptance`, `Definition of Done` |

### Recommended Sections

| Section | Purpose | Aliases |
|---------|---------|---------|
| **Why** | Context and rationale | `Goals`, `Summary`, `Motivation` |
| **Scope** | What the issue covers | `Background`, `Context`, `Overview` |
| **Non-Goals** | Explicit exclusions | `Out of Scope`, `Constraints` |
| **Implementation Notes** | Technical guidance | — |

---

## Writing Good Tasks

Each task should be:
- **Specific** — Clear enough to verify completion
- **Small** — Completable in one iteration
- **Actionable** — Starts with a verb

✅ Good:
```markdown
- [ ] Add input validation for email field in UserForm component
- [ ] Write unit tests for calculateDiscount function
- [ ] Update README with new API endpoints
```

❌ Bad:
```markdown
- [ ] Fix bugs
- [ ] Improve code
- [ ] Update things
```

---

## Writing Good Acceptance Criteria

Criteria should be:
- **Verifiable** — Can be objectively checked
- **Specific** — No ambiguity about pass/fail
- **Independent** — Each criterion stands alone

✅ Good:
```markdown
- [ ] All unit tests pass
- [ ] API returns 400 status for invalid input
- [ ] Documentation includes usage examples
```

❌ Bad:
```markdown
- [ ] Code is good
- [ ] Works correctly
- [ ] Meets requirements
```

---

## Definition of Ready / Quality Bar

The tips above ("be specific") set the *average*. This section sets the *floor*:
the bar an issue must clear on the **first pass** so it does not bounce back for a
second round. An issue is **Ready** only when every item below holds. If a
candidate cannot meet it, it is not ready to file — send it back to the
generator, not to a human.

These rules are stricter than "be specific" because vague tasks and
unfalsifiable acceptance criteria are the exact failure that forces a second
pass.

### 1. Tasks must name a real, verified file / function / path

Every task must reference at least one concrete artifact — a file path, a
function or symbol name, a config key, a workflow job, or a command — **that the
author has confirmed exists in the current checkout** (or, for a create task,
the exact path that will be created and where it will be wired in). A task that
names no artifact is not actionable.

**Banned vague verbs (with no named target):** "fix bugs", "improve X",
"update things", "clean up", "refactor", "make it better", "handle errors",
"optimize", "polish", "enhance" — rejected unless paired with a named artifact
**and** an observable outcome.

If a cited file no longer matches current `main` (the gap was already fixed in
an unpulled PR), that is a defect, not a task: record `INSUFFICIENT_EVIDENCE`
and route to deeper review rather than fabricating.

| | Example |
|---|---|
| ❌ **Bad** | `- [ ] Fix the verifier so it handles the worst-case policy correctly` |
| ❌ **Bad** | `- [ ] Improve CI coverage for the langchain scripts` |
| ✅ **Good** | `- [ ] In .github/workflows/selftest-ci.yml, replace the single Python run step (line 77, currently python -m pytest tests/workflows/ -v) with an explicit file list that also runs tests/test_verdict_policy.py and tests/scripts/test_pr_verifier_compare.py` |
| ✅ **Good** | `- [ ] Add pydantic to the pip install line at selftest-ci.yml:73 so scripts/langchain/structured_output.py:8 (from pydantic import BaseModel) resolves under the slim selftest env` |

Rule of thumb: a reviewer who has never seen the repo should be able to open the
named file and see exactly where the change goes.

### 2. Acceptance Criteria must include at least one named, observable test gate

At least **one** acceptance criterion MUST be a **concrete, named** failing
test, smoke test, or documented live-verification gate tied to **observable
behavior** — not a restatement of the task and not a subjective adjective.

A qualifying criterion names one of:

- a specific test path / test id (e.g.
  `tests/test_verdict_policy.py::test_select_verdict_worst_policy`), **or**
- a specific runnable command and its expected observable result (e.g.
  `gh workflow run selftest-ci.yml` → the run log shows a non-zero collected
  count for the named test files), **or**
- a documented live-verification step tied to behavior a human or agent can
  observe (e.g. "POST /api/register with a malformed email returns HTTP 400 and
  body `{"error":"invalid email"}`", captured in the PR).

**Banned acceptance criteria:** "code is good", "works correctly", "meets
requirements", "tests pass" *with no named test*, "looks clean", "is
performant". Subjective adjectives (clean / nice / good / fast / better /
intuitive / polished) are rejected — replace with a measurable check.

> **Enforcement note:** the generator pipeline now rejects an issue body whose
> Acceptance Criteria block references **no** test, smoke test, or verification
> gate at all (a conservative string check for a test path/id, a runner command
> like `pytest` / `gh workflow run` / `npm test` / `curl`, or a `smoke` /
> `verif` token). An acceptance section of pure adjectives will not pass.

#### The deliberate-break pattern (recommended worked form)

To prove an acceptance criterion is *falsifiable* — that the named test would
actually catch the regression the issue is about — express at least one
criterion as a **deliberate break → named test must fail → revert** loop. This
is the single most effective guard against scaffold-only "green but tests
nothing" completions.

The three moving parts that make it Ready:

1. **The break is named and surgical** — an exact file, line range, and the
   exact mutation, not "flip a severity mapping somewhere."
2. **The failing test is named** — exact test id and the assertion it makes, so
   anyone can confirm the break actually trips *that* test.
3. **The revert is explicit** — the issue does not leave a deliberate break in
   the tree.

If the issue is not test-shaped (docs-only or a live-service change), substitute
a **documented live-verification gate**: the exact command/request, the exact
observable response, and where the evidence is captured. The bar is "observable
and falsifiable," not "must be a pytest."

### 3. Why must cite current evidence (file:line) and the specific missing behavior

The Why section must ground the issue in **current** evidence: at least one
`path:line` reference the author verified, plus an explicit statement of **what
behavior is missing or wrong**. "It would be nice to have X" is not evidence.
Distinguish **latent fragility** from a **current break**, and say which it is
(verified). Don't imply a fire when there isn't one.

### 4. Non-Goals must forbid scaffold-only / partial-completion-claimed-as-done

Non-Goals must include an explicit clause that **scaffold-only or partial
completion does not count as done**, phrased against the specific issue. This is
the clause that stops an agent from landing a green-but-empty change and
declaring victory.

✅ Good (issue-specific):

> Scaffold-only completion does NOT count: a green selftest run that collected
> **0** of the named contract tests is a failure of this issue. The
> deliberate-break acceptance criterion below must be demonstrated.

❌ Bad (generic, unenforceable): "Don't cut corners."

Non-Goals should also fence out adjacent work the agent might wander into.

---

## Pre-submit CHECKLIST (Definition of Ready)

Run this before an issue is accepted — by the human author **or** by the
generator/agent producing the body. If any box fails, the issue is not Ready;
fix the body (do not file it).

```text
DEFINITION OF READY — run before filing / accepting an issue

Tasks
[ ] Every task names a real file / function / path / command.
[ ] Every cited path:line was verified against the CURRENT checkout
    (or is an explicit create-path with its wire-in point named).
[ ] No banned vague verb stands alone ("fix bugs", "improve X",
    "update things", "clean up", "refactor", "optimize", "polish").
[ ] Each task is atomic — one checkbox = one discrete, verifiable change.

Acceptance Criteria
[ ] At least ONE criterion names a specific test / smoke test / command
    OR a documented live-verification gate tied to observable behavior.
[ ] At least ONE criterion uses the deliberate-break -> named-test-must-fail
    -> revert pattern (or, for non-test work, an explicit observable
    live-verification gate with captured evidence).
[ ] No subjective adjectives (clean/nice/good/fast/better/intuitive/polished).
[ ] No "tests pass" without naming WHICH test.

Why
[ ] Cites at least one verified path:line of current evidence.
[ ] States the design/readiness goal AND the specific missing/wrong behavior.
[ ] Says whether this is latent fragility or a current break (verified).

Non-Goals
[ ] Explicitly forbids scaffold-only / partial completion claimed as done,
    phrased against THIS issue.
[ ] Fences out adjacent surfaces the agent should not touch.

Structure
[ ] Contains the required sections: ## Tasks and ## Acceptance Criteria.
[ ] Contains the recommended sections: ## Why, ## Scope, ## Non-Goals,
    ## Implementation Notes.
[ ] Implementation Notes give a confirmed-green local reproduction command
    where applicable.
```

---

## Worked Examples That Meet the Bar

The two examples below are the target depth: every task names a verified
`file:line`, the acceptance criteria name concrete gates, and each uses the
deliberate-break pattern (Example A as a unit test, Example B as a live smoke
request).

### Worked Example A — CI / contract-test gap (test-shaped)

```markdown
## Why

This repo ships a workflow named "Selftest CI" whose documented purpose is to
run "the repository's own test suite" (`docs/ci/WORKFLOWS.md:215`). But its
Python leg runs exactly one command — `python -m pytest tests/workflows/ -v`
(`.github/workflows/selftest-ci.yml:77`). Verified: `pytest tests/workflows/
--collect-only` returns **0** matches for the load-bearing contract tests
`test_verdict_policy.py` and `test_pr_verifier_compare.py` — they live at the
`tests/` root and under `tests/scripts/`, not under `tests/workflows/`. So the
workflow that *names itself* the repo self-test does not cover the contracts it
exists to protect. This is **latent fragility, not a current break**: I ran the
targeted contract files and all pass today. Missing behavior: a regression in
`scripts/langchain/verdict_policy.py` could merge with a green named self-test.

## Scope

Workflows-repo-only CI self-test wiring. Extend the `test-python` job of
`.github/workflows/selftest-ci.yml` to explicitly collect and run the enumerated
contract test files (in addition to the existing `tests/workflows/` run),
install `pydantic`, and set `PYTHONPATH` to the repo root. Update the one-line
selftest description in `docs/ci/WORKFLOWS.md`.

## Non-Goals

- Do NOT modify the required Gate (`pr-00-gate.yml`); it already runs the full
  suite via `pyproject.toml` `testpaths` and stays the source of truth.
- Do NOT change `pyproject.toml` `testpaths`.
- Do NOT run the whole `tests/scripts/` directory as a glob: verified that
  `tests/scripts/test_update_versions_from_pypi.py` makes a **live PyPI network
  call**. Enumerate the specific contract files instead.
- Scaffold-only completion does NOT count: a green selftest run that collected
  **0** of the named contract tests is a failure of this issue.

## Tasks

- [ ] In `.github/workflows/selftest-ci.yml`, replace the single Python run step
  (line 77, currently `python -m pytest tests/workflows/ -v`) with an explicit
  file list that also runs `tests/test_verdict_policy.py` and the
  `tests/scripts/test_pr_verifier_*.py` contract files.
- [ ] Add `pydantic` to the `pip install` line at `selftest-ci.yml:73` so
  `scripts/langchain/structured_output.py:8` (`from pydantic import BaseModel`)
  resolves under the slim selftest env.
- [ ] Add `env: PYTHONPATH: ${{ github.workspace }}` to the Python run step so
  `from scripts.langchain...` imports resolve.
- [ ] Update the selftest-ci bullet at `docs/ci/WORKFLOWS.md:215` to state the
  job now also runs the verdict/verifier contract tests.
- [ ] Perform the deliberate-break verification (see Acceptance Criteria),
  capture the FAIL output, then revert the break before requesting review.

## Acceptance Criteria

- [ ] The `test-python` job of `selftest-ci.yml`, run via `gh workflow run
  selftest-ci.yml`, collects and passes the named groups with a non-zero count
  each. Demonstrated by the run log's collected count, not just a green check.
- [ ] **Deliberate-break gate:** temporarily edit
  `scripts/langchain/verdict_policy.py:12-17` to swap the `VERDICT_SEVERITY`
  ranks of `"concerns": 2` and `"fail": 3`. With this change,
  `tests/test_verdict_policy.py::test_select_verdict_worst_policy` (asserts
  `select_verdict(..., policy="worst") == "CONCERNS"`) **must FAIL** in the
  selftest-ci Python job. Revert the edit after capturing the failure.
- [ ] The selftest-ci Python job does NOT invoke
  `tests/scripts/test_update_versions_from_pypi.py` (confirm it is absent from
  the run log), so the self-test has no live-PyPI dependency.

## Implementation Notes

- Edit only `.github/workflows/selftest-ci.yml` (the `test-python` job) and one
  bullet in `docs/ci/WORKFLOWS.md:215`.
- Confirmed-green local reproduction from repo root:
  `PYTHONPATH=$(pwd) python -m pytest tests/test_verdict_policy.py tests/scripts/test_pr_verifier_compare.py -q` → passes.
```

### Worked Example B — application behavior gap (live-verification-shaped)

This shows the bar met when the deliberate-break gate targets **runtime
behavior** rather than a unit test, and the "test" is a smoke request.

```markdown
## Why

The registration endpoint accepts malformed email addresses, writing invalid
rows and breaking downstream notification sends. Verified: `src/api/register.ts:42`
calls `createUser(body)` with no email check, and `src/utils/validation.ts`
exports `isValidEmail` (line 11) that is **not imported anywhere in the API
layer** (`grep -rn isValidEmail src/api` returns no hits). The design contract
in `docs/api/registration.md:18` states "reject malformed emails with a 400."
Missing behavior: server-side rejection. This is a **current break** — a smoke
POST with `"not-an-email"` returns HTTP 201 today.

## Scope

Add server-side email validation to `POST /api/register` using the existing
`isValidEmail` util. Client-side and the email-verification flow are out of scope.

## Non-Goals

- Do NOT change the downstream email-verification flow or add new registration
  fields.
- Do NOT add a new validation library — reuse `src/utils/validation.ts`.
- Scaffold-only completion does NOT count: adding `isValidEmail` import without
  wiring it into the request path, or adding a test that does not actually
  exercise the 400 path, is a failure of this issue. The live-verification gate
  below must be demonstrated with captured request/response.

## Tasks

- [ ] In `src/api/register.ts` (before the `createUser(body)` call at line 42),
  call `isValidEmail(body.email)` from `src/utils/validation.ts:11` and return
  HTTP 400 `{"error":"invalid email"}` when it is false.
- [ ] Add a unit test `src/api/__tests__/register.test.ts` (`rejects malformed
  email`) asserting a 400 + the error body for input `"not-an-email"`.

## Acceptance Criteria

- [ ] Named test: `src/api/__tests__/register.test.ts` (`rejects malformed
  email`) passes, asserting HTTP 400 and body `{"error":"invalid email"}`.
- [ ] **Deliberate-break gate (live + test):** temporarily revert the guard in
  `src/api/register.ts` (delete the `isValidEmail` check). The named test above
  **must FAIL**, AND the smoke request `curl -i -X POST /api/register -d
  '{"email":"not-an-email"}'` must return `201` (the bug). Restore the guard;
  the test passes and the same smoke request returns `400`. Capture both
  request/response pairs in the PR.
- [ ] A valid email (`user@example.com`) still returns `201` and creates the
  user (smoke request captured in PR).

## Implementation Notes

- Reuse the existing util at `src/utils/validation.ts:11`; do not reimplement.
- Confirmed current behavior before change: `curl -i -X POST /api/register -d
  '{"email":"not-an-email"}'` → `HTTP/1.1 201 Created` (this is the break).
```

---

## Tips for LLMs Creating Issues

1. **Be specific about file paths** — Include exact paths in Implementation Notes
2. **Keep tasks atomic** — One checkbox = one discrete change
3. **Make criteria testable** — If you can't write a test for it, rephrase it
4. **Include context** — The Why section helps agents understand intent
5. **Set boundaries** — Non-Goals prevent scope creep

---

## Using the GitHub Issue Form

This repository includes an issue template at `.github/ISSUE_TEMPLATE/agent_task.yml` that enforces this structure. When creating issues through GitHub's UI, use the "Agent Task" template for proper formatting.

For programmatic issue creation, follow this format directly in the issue body.
