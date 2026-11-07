# Issue #4508 source verification

Reviewed source fix `37e23000` and PR #4510 follow-up commits through `8226bd56`.
The relevant source fix and regression tests are confined to CI history;
merged base changes are outside this task.

## Verified implementation

- [x] Locate the sync source: `.github/sync-manifest.yml` ships
  `scripts/ci_history.py` directly, without a separate consumer template.
- [x] Identify the conflicting annotations in `main()` at lines 119 and 152.
- [x] Keep `record` in the missing-report branch and use `failure_record` in
  the exception branch, preserving runtime output.
- [x] Verify the fixed source with mypy using an empty configuration, bypassing
  this repository's relaxed `scripts.*` override.
- [x] Run the consumer-layout regression tests for namespace and regular packages.
- [x] Reintroduce the duplicate annotation in the actual source, observe the named
  regression test fail with the original diagnostic, restore the source, and rerun
  successfully.
- [x] Extend the runtime error-path test to verify the appended NDJSON record,
  preservation of previous history, complete failure evidence, and GitHub metadata
  both present and absent.

Validation:

```text
python -m mypy --config-file <temporary-empty-mypy.ini> --no-incremental \
  --ignore-missing-imports --follow-imports=silent \
  --cache-dir <temporary-cache> scripts/ci_history.py
Success: no issues found in 1 source file

# Duplicate annotation temporarily restored, then reverted in a finally block:
python -m pytest tests/scripts/test_ci_history.py::test_ci_history_type_checks_under_consumer_mypy -m 'not slow' -q
1 failed: scripts/ci_history.py:152: error: Name "record" already defined on line 119 [no-redef]

# Fixed source restored:
python -m pytest tests/scripts/test_ci_history.py tests/workflows/test_ci_history.py tests/scripts/test_ci_metrics.py tests/workflows/test_ci_metrics.py -m 'not slow' -q
43 passed

ruff check tests/workflows/test_ci_history.py
All checks passed!
```

The broader `python -m pytest tests/ -m 'not slow' -q -x` run was interrupted
before completion; no full-suite success is claimed. The required repository-wide
Black command failed when Python 3.14's forkserver tried to bind a local socket
(`PermissionError: Operation not permitted`). A single-worker retry did not
return a result and was interrupted. The edited Python file was formatted at
line length 100 and passes `black --check --line-length 100
tests/workflows/test_ci_history.py`; the global formatting gate is not established.
A fork-worker compatibility retry also returned no result and was interrupted.

## Delivery verification remains external

- [ ] Confirm `Python CI / typecheck-mypy` succeeds on the regenerated
  `stranske/trip-planner#1957` head.
- [ ] Confirm the next sync-core round no longer reports this finding.

These are post-merge or human verification steps, outside the agent's local
completion criteria. The scheduled `.github/workflows/maint-68-sync-consumer-repos.yml`
must regenerate the consumer PR. The workflow file must not be modified or
manually triggered by this agent; the generated consumer PR must not be patched.

`gh run view 42325493922 --repo stranske/trip-planner --json conclusion,headSha,jobs`
could not connect to `api.github.com`. The GitHub connector independently confirmed
that the original run's job `128260180158` (`Python CI / typecheck-mypy`) failed.
That historical run does not establish success for a regenerated head.

PR checkbox reconciliation was attempted through the GitHub connector but blocked:
`MCP tool call requires approval, but approval policy is never`. The verified
checkboxes above record the reconciliation without claiming the remote PR body
was updated. PR #4510 was verified open and ready for review (`draft=false`).

The local commit is also blocked: `git add` cannot create `.git/index.lock`
because `.git` is mounted read-only. The source test change and this evidence
remain in the working tree for the automation runner to commit.

## Consumer-isolated mypy regression follow-up

Reviewed commits `ad3aa5b0` through `7dbd3397` before making further changes.
The source already uses `failure_record` in the exception branch, and the six
implementation tasks duplicated in the quoted source issue are verified complete.
The managed Automated Status Summary already records those implementation results;
the unchecked duplicates in the quoted issue do not represent missing code.

The consumer-layout regression now launches mypy as a bounded subprocess with
the temporary consumer checkout as its working directory. Both namespace and
regular packages resolve the copied `scripts` modules independently of Workflows'
checkout, configuration and in-process mypy state. The existing mutant cases
still restore the duplicate annotation in disposable copies and require the
original `Name "record" already defined` / `[no-redef]` diagnostic.

Verified in this follow-up:

```text
pytest tests/scripts/test_ci_history.py tests/workflows/test_ci_history.py tests/scripts/test_ci_metrics.py tests/workflows/test_ci_metrics.py -m 'not slow' -q
43 passed in 5.72s

python -m mypy --config-file <temporary-empty-mypy.ini> --no-incremental \
  --ignore-missing-imports --follow-imports=silent \
  --cache-dir <temporary-cache> scripts/ci_history.py
Success: no issues found in 1 source file

ruff check tests/scripts/test_ci_history.py
All checks passed!

black --check --line-length 100 tests/scripts/test_ci_history.py
1 file would be left unchanged.

git diff --check
Exit 0
```

Reconciliation of the quoted implementation checkboxes and deliberate-break
criterion was again attempted with `github_update_pull_request`. The connector
rejected the update: `MCP tool call requires approval, but approval policy is never`.
The prepared replacement body is at `/tmp/issue-4508-reconciled-pr-body.md` for
the runner; no remote checkbox update is claimed. PR #4510 was confirmed open
with `draft=false` before the attempted edit.

`gh run view 42325493922 --repo stranske/trip-planner --json conclusion,headSha,jobs`
again failed to connect to `api.github.com`. Regenerated consumer CI and the next
sync-core classification remain unchecked external verification. The protected
sync workflow must not be edited or triggered by this agent.

The broader `timeout 180 pytest tests/ -m 'not slow' -q -x` run exited 124 after
180 seconds, with progress at 2% and no final test result. The repository-wide
Black command was run with `BLACK_NUM_WORKERS=1` to avoid the earlier forkserver
restriction, but did not complete and was interrupted. Bounded verbose retries
also timed out; their partial file counts do not establish a full formatting pass.
The mandatory pre-commit formatting gate therefore remains unverified and no
commit was attempted in this follow-up. The workspace also mounts `.git`
read-only. The automation runner must finish that gate and commit the test change.

Final read-only verification confirmed PR #4510 is still open and ready for review
(`draft=false`).


## Package and file target regression verification

- [x] Extend the isolated consumer mypy regression to check both `scripts` and
  `scripts/ci_history.py` targets, for namespace and regular packages.
- [x] For each target/layout, confirm the fixed source passes and a disposable
  copy with the duplicate `record` annotation produces the original `[no-redef]`
  diagnostic.

Validation: the focused CI history and metrics command above now reports
**47 passed**. An independent empty-config mypy check of `scripts/ci_history.py`
reports **Success: no issues found in 1 source file**. Black (line length 100)
and Ruff both pass for the edited test; `git diff --check` passes.

The repository-wide Black command was attempted again with
`BLACK_NUM_WORKERS=1` and interrupted after stalling. A bounded two-file retry
also stalled; a traceback shows Black waiting in its asynchronous multi-file
runner with an idle thread worker. Individual-file Black succeeds. The global
formatting gate remains unverified; no commit was attempted. Staging the test
with `git add` separately confirms `.git/index.lock` cannot be created because
`.git` is read-only. The automation runner must finish the gate and commit.

`gh run view 42325493922 --repo stranske/trip-planner` cannot connect to
`api.github.com`; the read-only GitHub connector confirms the historical mypy
job failed and PR #4510 is open with `draft=false`. Regenerated consumer CI and
next-round sync-core classification remain unchecked post-merge verification.
The protected sync workflow must not be modified or triggered by this agent.

Reconciliation of the verified implementation checkboxes in PR #4510 was
attempted again and rejected: `MCP tool call requires approval, but approval
policy is never`. The remote PR body was not changed.

The broader `timeout 180 pytest tests/ -m 'not slow' -q -x` command exited 124
after 180 seconds at approximately 2% progress, without a final test result.
No full-suite success is claimed.

The new `file-target-namespace-shipped-source` regression was also run against
the actual source with `failure_record` temporarily renamed back to `record`:
it failed with the original `[no-redef]` diagnostic. The source was restored
byte-for-byte in `finally`, and the same test then passed (1 passed in 1.45s).
