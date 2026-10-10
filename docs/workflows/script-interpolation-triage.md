# Workflow script interpolation triage (#3016)

Follow-up to merged PR #3020. This documents the repository-wide review of
`${{ inputs.* }}` and `${{ github.event.* }}` expressions that appear inside
`run:` or `with.script:` block scalars.

## Summary

| Category | Count | Action |
| --- | ---: | --- |
| Free-text inputs moved to `env:` in #3020 | 3 fields | `commit_message`, `codex_args`, `repos` |
| Additional free-text input fixes | 3 fields | `target_repo`, `commit_prefix`, `head_repository` |
| Campaign output transport | Step outputs | Use step `env:` indirection |
| Verifier model input fixes | 2 fields | `model`, `model2` |
| Reviewed interpolation allowlist | 89 distinct tuples | Explicit allowlist in `test_no_untrusted_interpolation.py` (97 literal entries including duplicates) |

## Free-text inputs (must use `env:` indirection)

These workflow-dispatch or runner inputs are free-form text and must never
appear directly inside a `run:`/`script:` scalar:

- `inputs.commit_message` — fixed in #3020 (`maint-70`)
- `inputs.codex_args` — fixed in #3020 (`reusable-codex-run`)
- `inputs.repos` — fixed in #3020 (maint/health sync workflows)
- `inputs.target_repo` — fixed here (`maint-72`)
- `inputs.commit_prefix` — fixed here (`reusable-18-autofix`)
- `inputs.head_repository` — fixed here (`agents-keepalive-branch-sync`)
- `inputs.model`, `inputs.model2` — verifier evaluation/comparison environment transport

The regression guard bans these expressions in script bodies and fails if they
reappear.

## Constrained-value allowlist

The remaining 89 distinct `(workflow, step, expression)` tuples are the
historically reviewed inventory; an allowlist entry is not proof against a
new concrete counterexample. Their reviewed categories include:

- **Booleans / dry-run flags** — `inputs.dry_run`, `inputs.create_issue`, etc.
- **Numeric identifiers** — `inputs.pr_number`, `inputs.issue_number`, `github.event.issue.number`
- **Repo-controlled refs** — `github.event.pull_request.base.ref`, `github.event.repository.default_branch`
- **Enumerated modes** — `inputs.mode`, `inputs.agent_key`, `inputs.package-manager`, `inputs.test-runner`
- **Step output passthrough** — `steps.registered.outputs.repos` consumed via step `env:` in `maint-82`

Each tuple is recorded in `REVIEWED_SCRIPT_INTERPOLATIONS` inside
`tests/workflows/test_no_untrusted_interpolation.py`. Adding a new
`inputs.*`/`github.event.*` script interpolation requires updating that set and
this document.

The 2026-10-06 bounded verifier evidence-profile step shifts the existing
reusable verifier locations by one (12→13, 22→23, 28→29, 32→33). Subsequent
independent assessment showed that model/model2 are free text, not constrained
values: shell command substitution executed before argument construction.
Evaluation and comparison now transport model/model2 and provider via step
`env:` and quoted shell variables. Six obsolete allowlist occurrences were
removed; three existing enumerated mode occurrences remained at that checkpoint. Model
inputs are globally banned from script interpolation. Executable regression
tests preserve command-substitution and quote-breaking payloads as literal
arguments in both modes, with normal-model controls. The new profile likewise
uses `env:` and a fixed-value case statement, adding no exception.

The evaluate-capacity upload added in PR #3821 shifted the unified-verdict
step and exposed its positional allowlist dependency. A deliberate mode payload
executed shell command substitution in that step; the related auth precheck
used the same direct interpolation. Both now transport `inputs.mode` through
step `env:` and quoted shell variables. Their three obsolete allowlist entries
are removed, not moved or widened. Execution regressions cover substitution,
quote-breaking and ordinary evaluate/compare/checkbox controls.

## Test gate

`tests/workflows/test_no_untrusted_interpolation.py::test_no_untrusted_expressions_in_script_bodies`
parses every workflow file, walks `run:`/`script:` scalars, and asserts:

1. Banned free-text expressions do not appear.
2. Every other `inputs.*`/`github.event.*` hit is present in the reviewed allowlist.

Deliberate-break check (from issue acceptance criteria): re-introduce
`git commit -m "${{ inputs.commit_message }}"` in `maint-70` and confirm the
named test fails.
