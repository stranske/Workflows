WF#4082 verification on 2026-11-07, checkout `b1b568f2`.

The first unchecked task is verified. The issue-format guide's current path is
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate lists
remain `[opened, synchronize, reopened, ready_for_review]`. The compiled manifest
retains create-only Gate delivery, Template overwrite and the reasoned
Manager-Database skip. No workflow or manifest was edited.

The new two-case scanner integration test uses the real compiled Gate entry and
registered roster, with simulated remote contents. It proves ordinary create-only
and skipped custom Gates remain visible in FYI trigger reporting without producing
actionable whole-file drift, while Template's overwrite exception still reports
actionable drift. It checks console, JSON and Markdown output and verifies each
differing consumer blob is read exactly once. This complements the existing
matching, extra, missing and failed-read tests. Black also formatted the touched
test file; an unused result assignment in its existing failed-read test was removed.

Validation uses Health 68's selected Python 3.14 (runner Python 3.14.10):

```bash
python3 -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 171 passed in 21.04 seconds. Expanded suite: 173 passed in 22.16 seconds.
After final test cleanup, the two new cases and three post-selection failed-read
cases pass (5 passed, 82 deselected in 1.53 seconds). Ruff and whitespace checks pass.
Targeted Black passes at line length 100. The exact required repository-wide Black
command was attempted and rejected by the sandbox's multiprocessing socket restriction.
The same repository-wide scope passes with the established sandbox single-worker
fallback: exit 0, 909 files unchanged. An initial 55-second attempt timed out;
the bounded 110-second attempt completed. Exact commands are recorded in
`verification-round-8.json`. The fallback retains Black's formatting and safety checks.

Before editing, the real-input acceptance command was recorded at
2026-11-07T02:45:47.873448Z, with one attempt, no retries and a 110-second timeout:

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round8/summary.md --report-json /tmp/issue-4082-round8/drift.json
```

It exits 1 in 0.439 seconds, preserving 16 explicit Gate unknowns and no all-match
because authenticated runner reads are unavailable. No production repair is justified
by this expected failure. All 30 requested `gh pr view`/`gh pr diff` attempts and
16 authenticated `gh api` Gate reads fail to connect. These 46 reads took 0.952
seconds, with one attempt per command and a 10-second per-request stop rule.
Exact attempted commands and failures are in `/tmp/issue-4082-round8/cli-reads.json`;
their command patterns, coverage, date and shared failure are retained in the JSON
report. The roster script runs successfully; `~/.codex/bin/handoff.sh` is absent.

Authenticated connected GitHub metadata and complete paginated patches separately
confirm all 14 campaign PRs remove only `labeled` in one changed line, cite #3983
and #4082, retain their source marker and have `autofix`/`automerge` labels. Thirteen
are merged; PAEM#2390 remains open and ready at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`. Its directly inspected unresolved
[review thread](https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2390#discussion_r4305945127)
concerns losing the `verify:full` label wakeup. Preserve this explicit disposition;
do not assume an owner dependency, silently resolve it, close the PR or change its
workflow under standard-agent restrictions. Workflows#4084 is merged; its complete
five-file patch, Health 68 command, current scanner and tests were inspected.

Prepared campaign merge checklist for WF#4082 (current connected metadata):

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
- [x] https://github.com/stranske/Workflows/pull/4084 — merged 2026-10-18T06:29:45Z

Connected default-branch reads independently show matching trigger lists in all
16 registered consumers, including Manager-Database and PAEM. No new campaign PR
is needed from this roster. These reads do not satisfy the requested runner Health
68 result after all campaign merges. The JSON report records each file SHA,
trigger list, campaign head/merge state, labels and diff verification.

The final campaign merge timestamp remains undetermined while PAEM#2390 is open.
The 48-hour observation interval and exact completion time therefore cannot yet be
established; numerator, denominator and percentage are unknown, not zero. After
the remaining campaign disposition, verify final `mergedAt`, perform successful
authenticated runner readback and collect the complete ensuing interval with
`python3 scripts/measure_gate_cancellations.py --merge "$FINAL_CAMPAIGN_MERGED_AT" --output /tmp/gate-observation.json`.
No historical interval is substituted for the required final campaign interval.

`git add` fails with exit 128 because `.git/index.lock` cannot be created on the
read-only filesystem. No commit or push occurred. The tested source diff is also
prepared at `/tmp/issue-4082-round8/gate-policy-tests.patch`. An authorized parent
must run the exact formatting gate in an environment that permits it, commit the
prepared source/test change and
publish the evidence. `pr-body-round-8.md` preserves the current PR body with only
the independently verified first task newly checked; all other checkboxes remain.

Automatic approval review rejected both the PR checkbox update and `needs-human`
label, as well as the WF#4082 evidence comment, with
`MCP tool call requires approval, but approval policy is never`.
No remote publication is claimed. This note is the prepared source-issue comment.
Final connected metadata readback confirms Workflows#4503 and PAEM#2390 remain
open and non-draft at their previously inspected heads.
