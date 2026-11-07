WF#4082 verification on 2026-11-07, checkout `88fc1d0d`.

The first unchecked task is verified. The issue-format guide is now at
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate lists
remain `[opened, synchronize, reopened, ready_for_review]`. Manifest behavior
remains create-only, with Template overwrite and the reasoned Manager-Database
skip. Existing source and scanner integration tests verify those policy boundaries.

Recent commits `88fc1d0d`, `b1b568f2` and `0facba3f` were reviewed. They add policy
integration tests, retain failed collection commands, and sanitize post-selection
request failures. The baseline focused suite passes: 173 tests in 19.54 seconds.
The PR body still has only its original acceptance checkbox checked. The prepared
body checks tasks 1, 2 and 4 after source, test and current metadata verification.

Before editing code, recorded the real-input command, interpreter, date and stop
rule in `outcome-round-9.json`: one attempt, no retries, 110-second deadline.
Health 68 selects Python 3.14; this runner uses Python 3.14.10.

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round9/summary.md --report-json /tmp/issue-4082-round9/drift.json
```

At 2026-11-07T02:58:13Z it exits 1 in 0.783 seconds with 16 explicit unknowns.
It does not establish live all-match. No scanner production repair is justified
by this expected authentication failure. All 30 requested gh PR view/diff commands
and 16 gh API Gate reads fail to connect. Their actual commands, roster, check date
and common failure are recorded in the outcome JSON. The roster script succeeded;
`~/.codex/bin/handoff.sh` is absent.

The scoped source change advances the observation task's requirement to exclude
runs outside the interval. The collector previously required a final conclusion
before filtering dates, so an unfinished run at the exclusive upper boundary
could block a completed observation. Three local regression cases (before, at
the end, and after the interval) fail before the fix. Date filtering now precedes
conclusion validation. Five additional in-interval cases retain fail-closed
behavior at the beginning and last second of the interval. This regression is
fixture-based; it is not evidence of a live campaign observation.

Validation:

```bash
python3 -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Result: 181 passed in 19.07 seconds. Ruff and whitespace checks pass.
Black formatted both changed Python files individually at line length 100.
The required command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
was attempted and fails because the sandbox denies Black's multiprocessing
socket. The established single-worker sandbox fallback completes with exit 0,
909 files unchanged, retaining Black's formatting and safety checks:

```bash
timeout 110s python3 -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Current connected GitHub metadata and complete paginated patches separately
confirm the 14 campaign patches each remove only `labeled`, with one addition
and one deletion in the sole changed file `.github/workflows/pr-00-gate.yml`.
All retain #3983, #4082 and the workflow-source marker. No duplicate PR was created.
Workflows#4084's five-file patch, scanner implementation and tests were inspected.
Prepared campaign merge checklist for WF#4082:

- [x] https://github.com/stranske/Counter_Risk/pull/1178 — 2026-10-18T07:55:16Z
- [x] https://github.com/stranske/Deliverable-Render/pull/101 — 2026-10-18T07:55:21Z
- [x] https://github.com/stranske/Doc-Lineage/pull/138 — 2026-10-18T07:55:24Z
- [x] https://github.com/stranske/Fine-Art-Archive/pull/832 — 2026-10-18T07:55:29Z
- [x] https://github.com/stranske/Inv-Man-Intake/pull/1037 — 2026-10-18T07:55:34Z
- [x] https://github.com/stranske/Manager-Mosaic/pull/116 — 2026-10-18T07:55:39Z
- [x] https://github.com/stranske/Orchestrator/pull/732 — 2026-10-18T07:55:43Z
- [x] https://github.com/stranske/Pension-Data/pull/979 — 2026-10-18T07:55:48Z
- [ ] https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2390 — open, ready; verify:full review unresolved
- [x] https://github.com/stranske/Ready/pull/633 — 2026-10-18T14:51:47Z
- [x] https://github.com/stranske/Travel-Plan-Permission/pull/1682 — 2026-10-18T07:55:57Z
- [x] https://github.com/stranske/Trend_Model_Project/pull/6112 — 2026-10-18T07:56:04Z
- [x] https://github.com/stranske/learning-management-system/pull/775 — 2026-10-18T07:56:09Z
- [x] https://github.com/stranske/trip-planner/pull/1921 — 2026-10-18T07:56:14Z
- [x] https://github.com/stranske/Workflows/pull/4084 — 2026-10-18T06:29:45Z

PAEM#2390 was directly inspected at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`. Its current non-outdated unresolved
[review thread](https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2390#discussion_r4305945127)
concerns the `verify:full` label wakeup; this is its explicit review disposition.
Connected default-branch Gate reads independently show matching trigger lists in
all 16 registered consumers. File SHAs, read ranges and trigger lines are retained
in `reconciliation-round-9.json`. These partial-file connected reads do not
substitute for authenticated runner readback after all campaign merges.

The final campaign merge timestamp remains undetermined while PAEM#2390 is open.
Its plus-48-hour completion time therefore cannot be established. Numerator,
denominator and percentage remain unknown, not zero. Required follow-up is the
existing PAEM campaign disposition, verified final mergedAt, successful runner
Health 68 readback, then the complete paginated 48-hour collection:

```bash
python3 scripts/measure_gate_cancellations.py --merge "$FINAL_CAMPAIGN_MERGED_AT" --output /tmp/gate-observation.json
```

Git staging fails with exit 128 because `.git/index.lock` cannot be created on
the read-only filesystem. No commit or push occurred. The source/test/doc diff is
prepared at `/tmp/issue-4082-round9/collector-interval.patch`. An authorized parent
must complete the required formatting gate, commit these files and publish the
prepared evidence and reconciled body. Workflow files were not edited.

Automatic approval review rejected the PR checkbox update, `needs-human` label,
and WF#4082 comment with
`MCP tool call requires approval, but approval policy is never`.
No remote publication is claimed. Final metadata confirms Workflows#4503 and
PAEM#2390 remain open and non-draft at their inspected heads.
