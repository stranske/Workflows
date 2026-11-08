WF#4082 verification — 2026-11-07, checkout `625b7754`.

Recent commits `625b7754`, `88fc1d0d`, `b1b568f2` and `0facba3f` were
reviewed before continuing. They implement the scanner's unknown-read reporting,
policy regressions and bounded observation collector. The baseline focused suite
passes: 181 tests in 14.13 seconds.

Tasks 1, 2 and 4 are verified. The issue-format guide now lives at
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate
types remain `[opened, synchronize, reopened, ready_for_review]`. The manifest
remains create-only, with Template overwrite and the reasoned Manager-Database
skip. No workflow, template or manifest was edited. The prepared reconciled body
is `pr-body-round-10.md`; remote publication was refused.

Current connected GitHub metadata and complete patches establish that all 14
campaign PRs change one line in the sole Gate file, removing only `labeled`.
Thirteen are merged; PAEM#2390 remains open and non-draft at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`.
Its non-outdated unresolved review thread
https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2390#discussion_r4305945127
concerns the `verify:full` label wakeup. This is the verified remaining review
disposition, not an assumed owner dependency. Resolving that contract may need
privileged workflow work; this standard run made no such edit or duplicate PR.
Workflows#4084 remains merged at 2026-10-18T06:29:45Z; its five-file patch,
scanner implementation and associated tests were inspected. Exact campaign heads,
merge times and patches are in `reconciliation-round-10.json`. A publishable
WF#4082 campaign checklist is in `issue-comment-round-10.md`.

Before code changes, recorded the real-input command, interpreter, timestamp and
one-attempt, 110-second stop rule in `outcome-round-10.json`.
Health 68 selects Python 3.14; this runner uses Python 3.14.10.

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round10/summary.md --report-json /tmp/issue-4082-round10/drift.json
```

At 2026-11-07T03:07:05Z the command exits 1 in 0.287 seconds, reporting all
16 registered consumers unknown. It does not print all-match. The absent
`~/.codex/bin/handoff.sh` prevents additional lane-roster discovery. All 30
requested runner gh PR view/diff commands and all 16 authenticated gh API Gate
reads fail to connect; commands, date and failures are retained in the outcome
JSON. No scanner production repair is justified by unavailable authentication/networking.

The scoped code change advances the observation task: the collector now passes
`--all` to `gh run list`, preserving historical runs if Gate is later disabled.
The installed CLI's `gh run list --help` explicitly requires this flag to
resolve a disabled workflow by name. A fixture regression with active and
disabled consumers failed before the fix (`incomplete` instead of `complete`)
and passes afterward, retaining both consumers' runs, commands and aggregate
counts. These fixture counts are not live campaign observation evidence.

Validation:

```bash
python3 -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Result: 182 passed in 14.03 seconds. Adding
`tests/workflows/test_health_68_liveness.py` to that command yields
190 passed, 1 failed in 14.17 seconds. The existing live execution probe fails
because its gh API call cannot connect; no test was skipped or disabled.
Ruff and `git diff --check` pass. Black formatted the changed files individually
at line length 100. The required repository-wide command was attempted:

```bash
black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

It fails with PermissionError when Python's multiprocessing forkserver binds a
socket forbidden by the sandbox. A single-worker attempt stalled and was stopped;
it does not count as a passing formatting gate. No commit or push was attempted.
Staging was attempted separately and failed with exit 128 because
`.git/index.lock` cannot be created on the read-only filesystem.

The source/test/doc change is prepared in the checkout and in
`/tmp/issue-4082-round10/collector-disabled.patch`. An authorized parent must
complete the formatting gate and commit it. The final campaign merge timestamp
and exact ensuing 48-hour end remain undetermined while PAEM#2390 is open.
Numerator, denominator and percentage are unknown, not zero. After resolving
the campaign disposition, verify the final mergedAt, obtain successful live
Health 68 readback, then run:

```bash
python3 scripts/measure_gate_cancellations.py --merge "$FINAL_CAMPAIGN_MERGED_AT" --output /tmp/gate-observation.json
```

Automatic approval review rejected the PR checkbox update, `needs-human` label
and WF#4082 comment: `MCP tool call requires approval, but approval policy is never`.
Their prepared text is retained locally; no remote update is claimed.
