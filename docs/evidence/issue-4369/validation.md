# Issue 4369 validation receipt

## Invocation regression and evidence at 995a04a8

On 2026-11-05, PR 4444 was open and non-draft at incoming head
`995a04a88c91e80a030c2a33a0814e1bbcf8c1b0`. Decoded hosted logs provide:

| Gate 41953876791 job | Result |
| --- | --- |
| [Python 3.13](https://github.com/stranske/Workflows/actions/runs/41953876791/job/127004919840) | 50,429 passed, 27 skipped, 3 xfailed in 625.42s |
| [Python 3.14](https://github.com/stranske/Workflows/actions/runs/41953876791/job/127004919855) | 50,429 passed, 27 skipped, 3 xfailed in 510.34s |
| [JavaScript](https://github.com/stranske/Workflows/actions/runs/41953876791/job/127004628902) | 3,369 passed, 0 failed, 1 skipped; 3,370 total |
| test-quality, job 127004628926 | Success, including deliberate-break acceptance |

Python ran on synthetic merge `e4a2dcb3382a1e857efe26a49ad5d19d1387b493`,
combining incoming head `995a04a8` with base
`cb380fbef7618e173d5fb61967b273a5904b6a6e`. Selection was
`not quarantine and not slow`; this does not prove unrestricted Python acceptance.
[Selftest CI 41953876723](https://github.com/stranske/Workflows/actions/runs/41953876723)
still reports two failures and seven passes on each slow compatibility runtime.
The failures remain `TestConsumerRepoSampling::test_simulated_consumer_repo_sync`
and `TestConsumerRepoSampling::test_autofix_versions_env_not_stale`, reporting
stale tool versions. No check is waived or protected file changed.

The added source/template invocation regression uses an empty auth file in a
custom directory outside HOME, and intercepts the subprocess boundary. It proves
that the real availability check permits invocation and the child receives that
same `CLAUDE_CONFIG_DIR`. No CLI or model is executed, and availability is not mocked.

Local Python 3.14.9 command:
`python -m pytest -p no:langsmith_plugin -q tests/test_subscription_llm.py -m 'not slow'`.
The optional LangSmith startup exclusion has the same reason documented below.

| Local state | Exit | Result |
| --- | --- | --- |
| Incoming tests | 0 | 18 passed in 0.50s |
| Extended tests | 0 | 20 passed in 0.49s |
| Source lookup restored to the old default; new invocation cases only | 1 | 1 failed, 1 passed, 18 deselected in 0.48s |
| Source restored; entire targeted file | 0 | 20 passed in 0.51s |
| Source child environment drops configured directory; new invocation cases only | 1 | 1 failed, 1 passed, 18 deselected in 0.54s |
| Source restored; entire targeted file | 0 | 20 passed in 0.51s |
| Template lookup restored to the old default; new invocation cases only | 1 | 1 failed, 1 passed, 18 deselected in 0.51s |
| Template restored; entire targeted file | 0 | 20 passed in 0.52s |
| Template child environment drops configured directory; new invocation cases only | 1 | 1 failed, 1 passed, 18 deselected in 0.49s |
| Template restored; entire targeted file | 0 | 20 passed in 0.48s |

Each mutation was reverted in a `finally` block. Both production files match
incoming HEAD byte-for-byte. Black formatting of the changed test, Ruff,
`git diff --check`, and the unchanged Gate diff-quality detector pass.
The repository-wide `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` returned exit 0: **889 files would be
left unchanged**. It used `BLACK_NUM_WORKERS=1`; stalled completion callbacks
required an external wakeup before Black printed its successful final report.
The hosted results above predate this new regression and must not be attributed
to a subsequent head. No full local Python suite or CI retry was run.

Publishing remains blocked: `git add` cannot create `.git/index.lock` on the
read-only filesystem. Connected GitHub blob creation, the blocker comment, and
the `needs-human` label each returned `MCP tool call requires approval, but
approval policy is never`. No remote write or new commit succeeded. The local
test/evidence changes need capture in an authorized environment before
resulting-head CI can establish acceptance.

The first unchecked task remains pending full source-gate evidence and disposition
of Selftest CI. The review thread `discussion_r4468176159` remains unresolved,
and guarded delivery remains assigned to the authorized closer. Post-merge
acceptance still requires normal Maint 68 regeneration and Maint 71 reporting
for Portable-Alpha-Extension-Model#2454 and absence of sync-core recurrence.

## Follow-up reconciliation at daf1ac21

On 2026-11-05, reviewed `c861aefb` through incoming head
`daf1ac2111066d0ad342774e101434a9d4d0e9bb`. The source/template fix and strict
boolean assertions are preserved; the previous iteration added missing-directory
cases. The incoming targeted suite passes all 14 cases. PR 4444 is open and
non-draft. The first task remains complete; the other three remain pending.

Current incoming-head hosted evidence is newer than the historical evidence below:

| Gate 41951003965 job | Result |
| --- | --- |
| [Python 3.13](https://github.com/stranske/Workflows/actions/runs/41951003965/job/126996000902) | 50,425 passed, 27 skipped, 3 xfailed in 431.22s |
| [Python 3.14](https://github.com/stranske/Workflows/actions/runs/41951003965/job/126996000862) | 50,425 passed, 27 skipped, 3 xfailed in 702.57s |
| [JavaScript](https://github.com/stranske/Workflows/actions/runs/41951003965/job/126995209543) | 3,369 passed, 0 failed, 1 skipped; 3,370 total |
| test-quality | Success, including deliberate-break acceptance |

Decoded logs bind these jobs to synthetic merge
`4435a2a2ec433dd50ce488bdee7655d1d2951b13`, containing PR head `daf1ac21`.
Python selection remains `not quarantine and not slow`, so this is not proof of
an unrestricted `python3 -m pytest -q tests/` pass.
[Selftest CI 41951003828](https://github.com/stranske/Workflows/actions/runs/41951003828)
still fails both slow compatibility runtimes: 2 failed, 7 passed on each.
The failing cases are
`TestConsumerRepoSampling::test_simulated_consumer_repo_sync` and
`TestConsumerRepoSampling::test_autofix_versions_env_not_stale`, reporting stale
tool versions. No required check is waived, and no protected file was edited.

The local follow-up adds a negative configured-directory state: an auth entry
named `.credentials.json` that is itself a directory. Availability must remain
false, including when default-directory auth exists. These four added
source/template cases verify the existing regular-file requirement.

Using `python -m pytest -p no:langsmith_plugin -q tests/test_subscription_llm.py
-m 'not slow'` on Python 3.14.10:

| Local state | Exit | Result |
| --- | --- | --- |
| Extended tests, fixed source/template | 0 | 18 passed in 0.53s |
| Source lookup restored to `Path.home() / ".claude"` | 1 | 4 failed, 14 passed in 0.55s |
| Source restored | 0 | 18 passed in 0.53s |
| Template lookup restored to `Path.home() / ".claude"` | 1 | 4 failed, 14 passed in 0.54s |
| Template restored | 0 | 18 passed in 0.53s |
| Source auth check weakened from `is_file()` to `exists()` | 1 | 2 failed, 16 passed in 0.54s |
| Template auth check weakened from `is_file()` to `exists()` | 1 | 2 failed, 16 passed in 0.54s |
| Both production files restored | 0 | 18 passed in 0.53s |

Each mutation was independently reverted in a `finally` block; both production
files match incoming HEAD byte-for-byte. Black formatting of the changed test,
Ruff, `git diff --check`, and the unchanged Gate diff-quality detector pass.
The required repository-wide `black --check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .` also passes: **889 files would be left
unchanged**. As in the earlier run below, the sandbox blocks multiprocessing
sockets and thread wakeups; the successful CLI invocation used
`BLACK_NUM_WORKERS=1` and an event-loop heartbeat in a temporary `/tmp`
startup module. File selection, formatting rules, and check behavior were
unchanged. No local full Python suite or CI retry was run.
These local results do not substitute for hosted CI on a subsequent head.

Publishing remains blocked in this environment. `git add` fails because
`.git/index.lock` is on a read-only filesystem. The connected GitHub tool rejects
PR-body reconciliation, the blocker comment, and the `needs-human` label with
`MCP tool call requires approval, but approval policy is never`. No remote write
succeeded and no checkbox was advanced. An authorized environment must capture
the local test/evidence changes, obtain resulting-head CI, assess Selftest CI,
and hand off discussion resolution and guarded delivery to the authorized closer.
Downstream acceptance remains pending normal Maint 68 regeneration and Maint 71
reporting, including the finding on Portable-Alpha-Extension-Model#2454 and
sync-core recurrence. No generated consumer branch was edited.

## Hosted evidence at the incoming head

Incoming head: `04eed694908259f5afbf5be0dc798c7f6afde10f`.
PR [4444](https://github.com/stranske/Workflows/pull/4444) was open and ready for
review when inspected on 2026-11-05. These results belong to that head, not to
the subsequent test extension in this commit.

The [Gate run](https://github.com/stranske/Workflows/actions/runs/41940960190)
completed successfully. Its decoded job logs report:

| Job | Result |
| --- | --- |
| [Python 3.13](https://github.com/stranske/Workflows/actions/runs/41940960190/job/126963800002) | 50,421 passed, 27 skipped, 3 xfailed in 410.50s |
| [Python 3.14](https://github.com/stranske/Workflows/actions/runs/41940960190/job/126963799916) | 50,421 passed, 27 skipped, 3 xfailed in 702.79s |
| [JavaScript](https://github.com/stranske/Workflows/actions/runs/41940960190/job/126962165036) | 3,369 passed, 0 failed, 1 skipped; 3,370 total |
| test-quality | Passed, including the deliberate-break acceptance step |

The Python Gate uses the repository's `not quarantine and not slow` selection;
these results do not establish that every test in an unrestricted `pytest tests/`
invocation passed.

[Selftest CI](https://github.com/stranske/Workflows/actions/runs/41940960182)
failed on both slow compatibility runtimes, each reporting 2 failed and 7 passed.
The failures were
`TestConsumerRepoSampling::test_simulated_consumer_repo_sync` and
`TestConsumerRepoSampling::test_autofix_versions_env_not_stale` in
`tests/scripts/test_update_versions_from_pypi.py`; both reported stale tool
versions. No protected version file or workflow was changed to address them.
The authorized closer must assess these results against the delivery gates.

## Regression extension and local verification

The existing source/template cases remain covered. The negative test now also
checks a nonexistent `CLAUDE_CONFIG_DIR`, both with and without default-directory
credentials. An explicit configured directory must not fall back to the default
directory merely because the configured directory is absent.

On Python 3.14.10, use:

```console
python -m pytest -p no:langsmith_plugin -q tests/test_subscription_llm.py -m 'not slow'
```

The installed optional LangSmith plugin raises an `asyncio.iscoroutinefunction`
deprecation warning during startup under the repository's warnings-as-errors
policy. Excluding that unrelated plugin allows the actual tests to execute;
the repository's test selection and warning policy remain unchanged.

| Local state | Exit | Pytest result |
| --- | --- | --- |
| Fixed source and template | 0 | 14 passed in 0.82s |
| Source lookup temporarily restored to `Path.home() / ".claude"` | 1 | 3 failed, 11 passed in 0.87s |
| Source restored | 0 | 14 passed in 0.82s |
| Template lookup temporarily restored to `Path.home() / ".claude"` | 1 | 3 failed, 11 passed in 0.88s |
| Template restored | 0 | 14 passed in 0.82s |

Each deliberate break failed the corresponding configured-directory positive
case and both negative cases with default credentials present, including the
new missing-directory case. Both production files were restored byte-for-byte
in a `finally` block after each experiment.

The full Black 26.10.1 CLI check passed with `--check --line-length 100 --exclude
'(\.workflows-lib|node_modules)' .`: **889 files would be left unchanged**. The
sandbox rejects multiprocessing socket creation, so the successful run used one
worker and a temporary event-loop heartbeat under `/tmp` to service completion
callbacks. The formatting checks and file selection were unchanged. Ruff on the
modified test, `git diff --check`, and `scripts/check_gate_diff_quality.py --base
origin/main --head HEAD` also passed.

A local full JavaScript run stalled and was interrupted; no local JavaScript
pass is claimed. The hosted JavaScript evidence above is retained with its exact
head. No local full Python suite or CI retry was performed.

## Delivery and downstream status

This run could not commit or publish its local changes. `git add` failed because
`.git/index.lock` cannot be created on the read-only filesystem. The connected
GitHub tools rejected blob creation, the blocker comment, and the `needs-human`
label because they require approval while the approval policy is `never`. No
remote write succeeded. The final read confirmed PR 4444 remains open, non-draft,
at the incoming head above. An authorized environment must capture these local
changes before collecting CI for the resulting head.

The review finding at `discussion_r4468176159` describes the earlier ledger-only
head. Both production copies now consult `CLAUDE_CONFIG_DIR`, and the regression
tests detect restoring the old behavior independently in each copy. Resolution
and guarded delivery remain assigned to the authorized closer; this receipt does
not resolve the thread or authorize bypassing any check.

Full source-gate acceptance remains pending evidence for the head containing this
test extension and disposition of the Selftest CI failures. No task checkbox is
advanced on the strength of an earlier head's CI alone.

Downstream acceptance remains pending after source delivery until normal Maint 68
regeneration and subsequent Maint 71 reporting establish that the finding on
`stranske/Portable-Alpha-Extension-Model#2454` cleared and sync-core no longer bumps
the source issue. No generated consumer branch was edited.
