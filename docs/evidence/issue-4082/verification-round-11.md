WF#4082 verification — 2026-11-07, checkout `1ed59d10`.

Reviewed the recent source/test commits and prior reconciliation before editing.
Tasks 1, 2 and 4 are verified; the reconciled body is `pr-body-round-11.md`.
The requested issue-format guide now resides at
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate types
remain `[opened, synchronize, reopened, ready_for_review]`. Manifest create-only,
Template overwrite and Manager-Database skip policy remain intact. No workflow,
template, manifest or protected file was edited.

Current connected GitHub metadata and complete patches verify all 14 campaign
changes remove only `labeled` in a one-line diff in the sole Gate file. Thirteen
are merged. PAEM#2390 remains open and ready at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`, with non-outdated unresolved review
thread 4305945127 concerning the `verify:full` wakeup. Its disposition was
inspected directly; no duplicate PR was created. Workflows#4084 remains merged
at 2026-10-18T06:29:45Z; its patch, scanner and tests were inspected. The absent
`~/.codex/bin/handoff.sh` prevents checking the additional supported-repo roster.

Before code changes, recorded the real-input command, interpreter, check date
and stop rule: one attempt, capped at 110 seconds. Health 68 selects Python 3.14;
this runner's selected interpreter is Python 3.14.10.

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round11/summary.md --report-json /tmp/issue-4082-round11/drift.json
```

At 2026-11-07T03:14:22Z this exited 1 in 0.427 seconds, reporting all 16
registered consumers unknown. All 16 authenticated `gh api` Gate reads and all
30 requested `gh pr view`/`gh pr diff` attempts failed to connect. Commands,
timestamps, repository coverage, current patches and output are retained in
`evidence-round-11.json`. Connected reads supplement reconciliation; they do not
establish successful Health 68 live readback. No scanner repair is justified
by unavailable runner authentication/networking.

Advanced the observation task by handling invalid `--merge` input as an argparse
usage error before any reads or report creation, preserving the whole-second
precision requirement. Added regressions for invalid/timezone-free/fractional
timestamps, non-list payloads, changed duplicate run IDs, invalid event/ID types
and zero-run status. Bad reads retain commands and unknown counts and cannot
pass. The shared 110-second collection budget is preserved to meet the required
under-two-minute bound; a per-consumer 110-second budget would violate it.

Validation:

```bash
python3 -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 182 passed in 21.21 seconds. After the change: 190 passed in 21.93
seconds. The collector's focused suite passed 44 tests in 0.86 seconds. Ruff and
`git diff --check` pass. Both Python files were formatted and checked individually
with Black at line length 100. The required repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
failed with PermissionError when its multiprocessing forkserver attempted a
sandbox-forbidden socket bind. A single-worker retry timed out at 110 seconds
(exit 124, 909 files reported unchanged); it is not a passing formatting gate.
No commit or push was attempted because the mandatory formatting gate did not
pass. This run also has read-only access to `.git`. Source changes are left in
the checkout for the authorized parent.

The final campaign merge timestamp and exact ensuing 48-hour completion time
remain undetermined while PAEM#2390 is open. Numerator, denominator and percentage
are unknown. No observation result or campaign completion is claimed. PR#4503
was verified open and non-draft before handoff.

Automatic approval review rejected the PR body update, `needs-human` label and
WF#4082 comment: `MCP tool call requires approval, but approval policy is never`.
Prepared task checkboxes and comment text are retained locally; no remote update
is claimed. The authorized parent must publish the reconciliation, address the
remaining workflow review within its permissions, obtain successful live
readback, verify the final merge timestamp and collect the complete 48-hour window.
