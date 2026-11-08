# Issue 4369 implementation report — 2026-11-08

The incoming checkout, `367b3f0e53fe8b10d43e27177662517af68e34cd`, already
contains the credential-path fix in `tools/subscription_llm.py` and its exact
consumer template. `_has_subscription_auth("claude")`, called by `available()`,
checks `.credentials.json` in `CLAUDE_CONFIG_DIR`, defaulting to `~/.claude` only
when the variable is absent. `build_environment()` passes that same variable to
the child CLI. The existing sync-manifest entry declares exact template parity;
no file ownership or distribution scope changed.

This iteration makes the existing regression tests selectable with the required
`claude_config_dir` expression. It adds a fixture-level subprocess tripwire and
extends configured-auth success to both absent and present default auth. The
configured directory is asserted to contain only the expected empty credential
file. HOME and auth environment variables are isolated, CLI discovery is mocked,
and invocation tests replace the tripwire with an inert subprocess stub. No real
Claude CLI or subscription is used. Missing/empty configured directories and a
credentials path that is itself a directory remain negative cases, including
when default credentials exist. Unset-variable cases retain default behavior.

## Regression proof

Every row uses the exact command:

```console
python3 -m pytest -q tests/ -k claude_config_dir
```

Python 3.14.10; wall time includes interpreter startup and collection. The incoming
test names selected no tests: exit 5, `50586 deselected in 29.17s`.

For the pre-fix experiment, both production copies temporarily replace only
`home = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))`
with `home = Path.home() / ".claude"`. After restoring both copies, the deliberate
break repeats that mutation in the source copy alone. Each mutation is restored
in `finally`; final production bytes match incoming HEAD. This reconstructs the
reported pre-fix path logic rather than claiming the entire checkout predates
the already-merged fix.

| Source state | Exit | Wall time | Observed pytest output |
| --- | --- | --- | --- |
| pre-fix | 1 | 13.75s | 12 failed, 12 passed, 50564 deselected in 9.65s |
| fixed | 0 | 13.60s | 24 passed, 50564 deselected in 9.52s |
| deliberate-break | 1 | 13.75s | 6 failed, 18 passed, 50564 deselected in 9.69s |
| restored | 0 | 13.60s | 24 passed, 50564 deselected in 9.60s |

The selected functions are:

- `test_claude_config_dir_available_with_credentials`
- `test_claude_config_dir_invocation_uses_configured_directory`
- `test_claude_config_dir_unavailable_without_credentials`
- `test_claude_config_dir_unset_uses_default_directory`

### pre-fix

```text
FAILED tests/test_subscription_llm.py::test_claude_config_dir_available_with_credentials[source-False] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_available_with_credentials[template-False] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[source-False] - RuntimeError: claude subscription CLI/auth unavailable
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[source-True] - Failed: DID NOT RAISE RuntimeError
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[template-False] - RuntimeError: claude subscription CLI/auth unavailable
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[template-True] - Failed: DID NOT RAISE RuntimeError
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-missing-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-empty-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-directory-entry-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[template-missing-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[template-empty-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[template-directory-entry-True] - assert (False,) == (True,)
12 failed, 12 passed, 50564 deselected in 9.65s
```

### fixed

```text
24 passed, 50564 deselected in 9.52s
```

### deliberate-break

```text
FAILED tests/test_subscription_llm.py::test_claude_config_dir_available_with_credentials[source-False] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[source-False] - RuntimeError: claude subscription CLI/auth unavailable
FAILED tests/test_subscription_llm.py::test_claude_config_dir_invocation_uses_configured_directory[source-True] - Failed: DID NOT RAISE RuntimeError
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-missing-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-empty-True] - assert (False,) == (True,)
FAILED tests/test_subscription_llm.py::test_claude_config_dir_unavailable_without_credentials[source-directory-entry-True] - assert (False,) == (True,)
6 failed, 18 passed, 50564 deselected in 9.69s
```

### restored

```text
24 passed, 50564 deselected in 9.60s
```

## Source gates and publication

Focused checks and full-suite attempts are recorded below.
A full-source pass is not inferred from the targeted results or earlier hosted CI.

`git add tests/test_subscription_llm.py` exits 128:

```text
fatal: Unable to create '/home/runner/work/Workflows/Workflows/.git/index.lock': Read-only file system
```

The session cannot write `.git` or `.agents`, so no commit or ledger update is
claimed. No workflow or protected security file was modified.

## Live downstream evidence checked on 2026-11-08

The earlier source repair PR [Workflows#4444](https://github.com/stranske/Workflows/pull/4444)
merged on 2026-11-05 as `d77a8e3ad93aaf4339fff0180bafa1264e3ec7c0`.
This is prior production delivery, independent of this iteration's unpublished
test improvements.

[Maint 68 run 41975139516](https://github.com/stranske/Workflows/actions/runs/41975139516),
consumer [job 127073790362](https://github.com/stranske/Workflows/actions/runs/41975139516/job/127073790362),
succeeded and reports source `d77a8e3ad93aaf4339fff0180bafa1264e3ec7c0` and
verified consumer commit `99d10a9838cecfb4327a2735d8f3723e393e413e`.
Reading `tools/subscription_llm.py` at that consumer commit confirms configured
credential-directory resolution.

The following [Maint 71 run 41976239018](https://github.com/stranske/Workflows/actions/runs/41976239018),
[job 127075733924](https://github.com/stranske/Workflows/actions/runs/41976239018/job/127075733924),
succeeded and reports that same consumer head and source. Its
`review_finding_disposition` has `raw_active_count: 4`, with discussion IDs
4434491631, 4434491646, 4434491667, and 4434491675. The scoped discussion
4434491702 / thread `PRRT_kwDOO15QxM6yXhfS` is absent. The plan is
`sha256:18dc9717229c216198a8b9241db7122f681f4ca8f90497ab88b6f37252dda4bf`.
Other findings still block that delivery; this is not an overall consumer merge
or all-findings-clear claim.

A current read of [the scoped review thread](https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2454#discussion_r4434491702)
reports `is_outdated=true`, `is_resolved=false`. Consumer PR 2454 remains open and
ready (`draft=false`) at `564d4bcd2ffa1eb08f1e033467618c569b45273a`.
The [issue 4369 comment history](https://github.com/stranske/Workflows/issues/4369)
contains no sync-core bump of this finding after regeneration. Its last
Portable-Alpha-specific recurrence is [comment 6649911684](https://github.com/stranske/Workflows/issues/4369#issuecomment-6649911684),
round `20261105T044440Z`, consumer head `39a3dc939133`, preceding the fixed head.
The last recurrence for any consumer is round `20261105T050113Z`. The newer
2026-11-08 opener comment is an opener restart, not a sync-core recurrence.
This establishes the requested historical post-delivery observation as of this
read; it does not predict future sync-core behavior or claim the thread was
explicitly resolved.

Current source PR [Workflows#4539](https://github.com/stranske/Workflows/pull/4539)
was read as open, ready (`draft=false`), at the incoming checkout head. No PR was
created, closed, merged, or converted to draft by this iteration.

## Final local check results

| Command | Exit | Observed result |
| --- | --- | --- |
| `python3 -m pytest -q tests/test_subscription_llm.py tests/workflows/test_subscription_llm_credential_canary.py -m 'not slow'` | 0 | 36 passed in 1.65s |
| `python3 -m ruff check tests/test_subscription_llm.py` | 0 | All checks passed |
| `black --line-length 100 tests/test_subscription_llm.py` | 0 | 1 file left unchanged |
| `black --check --line-length 100 tests/test_subscription_llm.py` | 0 | 1 file would be left unchanged |
| Repository Black check, runtime workaround described below | 0 | 890 files would be left unchanged |
| `git diff --check` | 0 | No whitespace errors |
| `git diff --exit-code -- tools/subscription_llm.py templates/consumer-repo/tools/subscription_llm.py` | 0 | Both production copies retain the incoming fix |
| `node --test .github/scripts/__tests__/*.test.js` | 130 | Stalled without a suite summary; interrupted |
| `timeout 120s node --test --test-timeout=60000 .github/scripts/__tests__/*.test.js` | 124 | Timed out without a suite summary |
| `timeout 600s python3 -m pytest -q tests/` | 130 | Interrupted after progress near 2%; no suite summary |
| `timeout -k 5s 180s python3 -m pytest -q tests/ -m 'not slow'` | 124 | Timed out near 2% without a suite summary |

Full JavaScript and Python source-gate acceptance remains **pending**. No existing
test was disabled or changed to address these broad-suite stalls.

The unmodified repository Black CLI attempt failed with `PermissionError: [Errno
1] Operation not permitted` when Python's multiprocessing forkserver tried to
bind a local socket. A one-worker attempt was interrupted; a 60-second retry with
a temporary event-loop heartbeat timed out after 856 files. The successful final
check used Black's normal CLI and full repository selection, with one worker and
the same temporary `/tmp/issue-4369-black-runtime/sitecustomize.py` heartbeat:

```console
BLACK_NUM_WORKERS=1 PYTHONPATH=/tmp/issue-4369-black-runtime timeout -k 5s 180s black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

The startup hook wraps `black.concurrency.maybe_use_uvloop()` and schedules a
callback every 0.05 seconds. It changes scheduling only; Black's formatting,
file selection, safe checks, and result reporting are unchanged. The hook is
outside the repository. The final command exited 0 and reported all 890 files.

Posting the blocker comment on PR 4539 was attempted after the implementation
and report were prepared. Automatic approval review rejected it:
`MCP tool call requires approval, but approval policy is never`. No comment was
posted. Remote publication is not a substitute for the blocked local commit.

The `needs-human` label attempt was also rejected with the same approval-policy
message. No label or PR-body checkbox update succeeded.

## Locally verified task checklist

These marks record inspected code, executed tests, and fetched live evidence.
They do not claim this iteration's test improvements were committed or published.
The two broad-gate items stay open because neither full suite passed locally.

- [x] Inspect Claude's `available()` implementation and child-CLI environment handling in `tools/subscription_llm.py`, identifying the existing credentials filename and default directory.
- [x] Add regression tests to the existing test module covering `tools/subscription_llm.py`, with test names containing `claude_config_dir`; isolate environment variables, home-directory credentials, CLI discovery, and other availability prerequisites so the tests exercise credential-path resolution without requiring a real subscription or invoking Claude.
- [x] In the `claude_config_dir` tests, set `CLAUDE_CONFIG_DIR` to a temporary directory containing only the expected credentials file and assert that Claude's `available()` returns `True`.
- [x] In the `claude_config_dir` tests, set `CLAUDE_CONFIG_DIR` to a directory without credentials and assert that Claude's `available()` returns `False`, including when credentials exist in the default directory.
- [x] Fix Claude's `available()` in `tools/subscription_llm.py` to resolve the credentials file relative to `CLAUDE_CONFIG_DIR` when set, consistently with the directory supplied to the child CLI.
- [x] Extend the tests covering `tools/subscription_llm.py` to verify that the existing default-directory behavior remains intact when `CLAUDE_CONFIG_DIR` is absent.
- [x] Run `python3 -m pytest -q tests/ -k claude_config_dir` against the pre-fix implementation, against the fix, and after deliberately restoring and then reverting the reported faulty path resolution; record commands, test names, exit codes, and before/after output in the implementation report.
- [ ] Run `node --test .github/scripts/__tests__/*.test.js` and `python3 -m pytest -q tests/` on the source fix and record their results.
- [x] After source delivery and regeneration by `.github/workflows/maint-68-sync-consumer-repos.yml`, inspect the next `.github/workflows/maint-71-merge-sync-prs.yml` run and the review thread on stranske/Portable-Alpha-Extension-Model#2454; record the consumer head, workflow run, thread state, and sync-core evidence, or explicitly report which live evidence is still pending.
- [x] Checked on the implementation date: `python3 -m pytest -q tests/ -k claude_config_dir` selects the new regression tests, exits zero, and completes in under two minutes using temporary credential directories without a real Claude invocation.
- [x] The configured-directory credentials test fails against the pre-fix credential-path logic and passes with the fix; the implementation report contains the observed outputs.
- [x] Restoring the reported faulty path resolution makes the named regression test fail; reverting that deliberate break makes it pass, with the final source retaining the fix.
- [x] The tests verify configured-directory credentials yield `True`, a configured directory without credentials yields `False`, and an unset `CLAUDE_CONFIG_DIR` preserves default-directory behavior.
- [ ] Both source gates pass: `node --test .github/scripts/__tests__/*.test.js` and `python3 -m pytest -q tests/`.
- [x] Post-merge live verification records that, after `.github/workflows/maint-68-sync-consumer-repos.yml` regenerates the candidate, the next `.github/workflows/maint-71-merge-sync-prs.yml` run reports stranske/Portable-Alpha-Extension-Model#2454 without this review thread and sync-core no longer bumps this finding. Source-test success alone does not establish this result; unavailable live evidence remains explicitly pending.
