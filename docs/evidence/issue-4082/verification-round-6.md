# WF#4082 verification, round 6

Reviewed commits aa9f8ef2 through b8e69fe8 before continuing. The scanner fixes
and existing tests support completion of tasks 1, 2 and 4 and the already checked
test acceptance criterion. `pr-body-round-6.md` reconciles those checkboxes;
publication was rejected by the connector's never-approval policy.

Task 1: the issue-format guide is under
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`; the requested root path is
absent. Root/template Gate types remain `[opened, synchronize, reopened,
ready_for_review]`. Manifest policy remains create-only, with Template in
`overwrite_repos` and the reasoned Manager-Database `skip_repos` exception.

Authenticated connected GitHub metadata and complete paginated patches confirm
all 14 campaign PRs still change exactly one line in the sole changed file,
`.github/workflows/pr-00-gate.yml`, removing only `labeled`. Thirteen are merged;
PAEM#2390 remains open, ready, unmerged at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`. Workflows#4084 is merged and its diff
was inspected. No duplicate PR was created. All 16 registered consumers were
read through connected GitHub's default-branch file API: their Gate activity
lists currently match, including Manager-Database and PAEM. This does not settle
PAEM#2390's disposition or establish the requested Health 68 command's result.
The current roster was obtained with `scripts/list_registered_consumer_repos.py`;
`~/.codex/bin/handoff.sh` is absent. See `campaign-reconciliation-round-6.json`.

Before edits, recorded one real-input Health 68 attempt at
2026-11-07T01:08:58.099113Z, with a 110-second stop rule and no network retries.
The runner-selected interpreter is Python 3.14.10. Runnable command:

```bash
repos_input=$(python3 scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python3 scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round6/summary.md --report-json /tmp/issue-4082-round6/drift.json
```

Exit 1 in 0.224 seconds, with all 16 Gates unknown and no all-match. Authenticated
runner `gh api` attempts for all 16 consumer Gate paths and `gh pr view`/`diff`
for every campaign PR fail to connect to api.github.com. Exact commands and
outputs are retained in the round-6 JSON evidence. This demonstrates unavailable
runner read access; no speculative scanner repair was made.

Added `scripts/measure_gate_cancellations.py` for the remaining observation task.
It uses the registered roster, authenticated `gh run list`, a total 110-second
read budget, automatic CLI pagination and bisection of saturated date windows.
It retains raw runs and successful query commands, removes boundary duplicates,
filters to the half-open 48-hour interval and never pairs runs across repos.
Unknown reads, unfinished runs, unfinished intervals and zero runs cannot pass.
The final merge timestamp must first be independently verified; the collector
does not confer authority to assume that an open campaign PR has merged.

```bash
timeout 110s python3 -m pytest tests/scripts/test_measure_gate_cancellations.py tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 141 passed. Final: 166 passed in 10.18 seconds, including 25 new
collector tests. Ruff, CLI `--help`, and `git diff --check` pass. Both Python
files were formatted with Black at line length 100. The required full-scope
Black command hit the sandbox's event-loop stall and timed out after reporting
909 files unchanged. The same complete scope passed with exit 0 using the
previously recorded sandbox workaround:

```bash
timeout 55s python3 -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Result: 909 files would be left unchanged. No exclusions or tests were disabled.

Staging/committing the scoped source, tests and evidence failed with exit 128:
`.git/index.lock` cannot be created on the read-only filesystem. No commit or
push is claimed. The connector rejected the PR-body update, `needs-human` label
and WF#4082 comment with `MCP tool call requires approval, but approval policy
is never`. The prepared body and comment are retained for an authorized parent.
Final readback confirms Workflows#4503 and PAEM#2390 are both open and non-draft.

Remaining: authorized publication, PAEM#2390 disposition, complete authenticated
Health 68 readback after campaign merges, and the ensuing 48-hour observation.
The final campaign merge timestamp and exact observation completion time remain
undetermined; numerator, denominator and percentage are uncollected, not zero.
No observation task or live acceptance checkbox was marked complete.
