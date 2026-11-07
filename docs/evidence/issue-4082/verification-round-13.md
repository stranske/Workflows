WF#4082 verification — 2026-11-07, checkout `39fc4f87`.

- [x] Inspect the issue-format guide, root/template Gate triggers and compiled
  manifest policy. The guide is at
  `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`; root/template types are
  `[opened, synchronize, reopened, ready_for_review]`. Create-only policy,
  Template's overwrite and Manager-Database's skip remain intact.

Extended the existing fleet integration test in
`tests/scripts/test_check_consumer_sync_drift.py` with missing-only and matching
trigger cases, using the real registry, compiled manifest and template. It now
verifies that matching triggers across consumers with different jobs produce
all-match without changing create-only or custom-Gate policy. Template body
drift remains actionable under its overwrite exception even when triggers match.
Missing-only triggers remain explicit in stdout, JSON and summary.

```bash
python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/scripts/test_measure_gate_cancellations.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 192 passed in 20.50s. After: 196 passed in 21.60s.
Focused Black, Ruff and `git diff --check` pass. Python 3.14.10 matches
Health 68's selected Python version. Before editing, the real-input command,
check date and stop rule (one attempt, 110 seconds maximum, no network retries)
were recorded. The command exited 1 in 0.515s, reporting unavailable reads for
all 16 registered consumers. The command and complete output are retained in
[evidence-round-13.json](evidence-round-13.json).

All 14 current campaign PR metadata records and complete file patches were
inspected through connected GitHub reads: every patch removes only `labeled`
in one changed line of `.github/workflows/pr-00-gate.yml`. Thirteen are merged.
PAEM#2390 remains open and non-draft at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`, with both required labels and source
references. Its review identifies a `verify:full` wakeup concern; no consumer
workflow was changed or duplicate PR created.

New supplemental default-branch connected reads show corrected triggers in
**all 16 registered consumers, including PAEM**. Repository names, blob SHAs,
trigger lists and campaign dispositions are in the JSON evidence. These reads
do not establish the specified authenticated runner `gh`/Health 68 acceptance.
All 46 requested runner PR/API commands failed to connect. The handoff script
is absent, so its additional supported-repo roster is unverified. Final campaign
mergedAt, observation interval and cancellation counts remain unestablished;
no guessed timestamp or partial-window measurement was used.

The mandatory repository-wide Black command was attempted:

```bash
BLACK_NUM_WORKERS=1 black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .
```

It did not finish and was interrupted (exit 130); this is not a pass. A separate
two-file check also timed out despite reporting both files well formatted.
No commit or push was attempted. Staging failed because `.git/index.lock` is on
a read-only filesystem. The source patch, proposed first-checkbox update and
issue comment are prepared under `/tmp/issue-4082-round13/` for the authorized
parent. No campaign acceptance checkbox is newly marked complete.

Automatic approval review rejected the PR checklist update, WF#4082 evidence
comment and `needs-human` label: `MCP tool call requires approval, but approval
policy is never`. No remote publication is claimed. The authorized parent must
publish the verified first-task status, resolve the remaining campaign PR's
disposition, obtain successful authenticated Health 68 readback and collect the
complete verified observation interval.
