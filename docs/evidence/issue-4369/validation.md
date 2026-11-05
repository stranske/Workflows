# Issue 4369 validation receipt

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
