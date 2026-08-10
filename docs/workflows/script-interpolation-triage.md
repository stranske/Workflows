# Workflow script interpolation triage (#3016)

Follow-up to merged PR #3020. This documents the repository-wide review of
`${{ inputs.* }}` and `${{ github.event.* }}` expressions that appear inside
`run:` or `with.script:` block scalars.

## Summary

| Category | Count | Action |
| --- | ---: | --- |
| Free-text inputs moved to `env:` in #3020 | 3 fields | `commit_message`, `codex_args`, `repos` |
| Additional free-text fixes in this PR | 4 fields | `target_repo`, `commit_prefix`, `head_repository`, campaign script outputs |
| Reviewed constrained interpolations | 103 | Explicit allowlist in `test_no_untrusted_interpolation.py` |

## Free-text inputs (must use `env:` indirection)

These workflow-dispatch or runner inputs are free-form text and must never
appear directly inside a `run:`/`script:` scalar:

- `inputs.commit_message` — fixed in #3020 (`maint-70`)
- `inputs.codex_args` — fixed in #3020 (`reusable-codex-run`)
- `inputs.repos` — fixed in #3020 (maint/health sync workflows)
- `inputs.target_repo` — fixed here (`maint-72`)
- `inputs.commit_prefix` — fixed here (`reusable-18-autofix`)
- `inputs.head_repository` — fixed here (`agents-keepalive-branch-sync`)

The regression guard bans these expressions in script bodies and fails if they
reappear.

## Constrained-value allowlist

The remaining 103 `(workflow, step, expression)` tuples are provably
constrained:

- **Booleans / dry-run flags** — `inputs.dry_run`, `inputs.create_issue`, etc.
- **Numeric identifiers** — `inputs.pr_number`, `inputs.issue_number`, `github.event.issue.number`
- **Repo-controlled refs** — `github.event.pull_request.base.ref`, `github.event.repository.default_branch`
- **Enumerated modes** — `inputs.mode`, `inputs.agent_key`, `inputs.provider`, `inputs.package-manager`, `inputs.test-runner`
- **Step output passthrough** — `steps.registered.outputs.repos` consumed via step `env:` in `maint-82`

Each tuple is recorded in `REVIEWED_SCRIPT_INTERPOLATIONS` inside
`tests/workflows/test_no_untrusted_interpolation.py`. Adding a new
`inputs.*`/`github.event.*` script interpolation requires updating that set and
this document.

## Test gate

`tests/workflows/test_no_untrusted_interpolation.py::test_no_untrusted_expressions_in_script_bodies`
parses every workflow file, walks `run:`/`script:` scalars, and asserts:

1. Banned free-text expressions do not appear.
2. Every other `inputs.*`/`github.event.*` hit is present in the reviewed allowlist.

Deliberate-break check (from issue acceptance criteria): re-introduce
`git commit -m "${{ inputs.commit_message }}"` in `maint-70` and confirm the
named test fails.
