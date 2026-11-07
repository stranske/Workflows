# WF#4082 verification, round 5

- [x] Inspect the issue-format guidance, Gate sync policy and root/template triggers.

`docs/AGENT_ISSUE_FORMAT.md` is absent; inspected its current source at
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Both Gate files retain
`[opened, synchronize, reopened, ready_for_review]`. The compiled manifest still
uses create-only delivery, overwrites only `stranske/Template`, and skips
`stranske/Manager-Database` with its custom-Gate reason. No workflow or protected
configuration was changed.

Added 12 real-configuration regression cases to
`tests/workflows/test_gate_trigger_contract.py`. Each loads the current registry,
manifest and template and simulates matching triggers, extra `labeled`, missing
`synchronize`, or an unavailable blob in Template, Manager-Database or the final
registered consumer. They require reads of every registered consumer, retain
custom-Gate diagnostics, and forbid all-match on drift or an unavailable read.
These are local tests, not live readback evidence. Scanner behavior was not
changed: the baseline demonstrated unavailable networking, not a new source bug.

Before-edit outcome check: 2026-11-07T00:44:03.788398Z. Interpreter:
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (runner-selected Python 3.14).
Command copied from Health 68's comparison step:

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round5/summary.md --report-json /tmp/issue-4082-round5/drift.json
```

Stop rule recorded before edits: one baseline and one post-test scan, each
capped at 110 seconds; no networking retries or speculative runtime repairs.
Baseline: exit 1 in 0.530 seconds. Post-test check at
2026-11-07T00:45:34.287981Z: exit 1 in 0.316 seconds. Both report all 16 registered
consumer Gates as unknown and no all-match. The full roster and output are in
`drift-outcome-round-5.json`. This does not satisfy authenticated readback.

Validation:

```bash
timeout 110s python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

Baseline: 129 passed in 4.91 seconds. After the change: 141 passed in
14.64 seconds. Ruff and `git diff --check` pass. Black formatted the changed file
at line length 100; full-repository formatting outcome is recorded below.

Runner `gh pr view`, `gh pr diff`, and `gh api` reads cannot connect to
api.github.com. Connected GitHub reads confirm Workflows#4084 is merged.
Portable-Alpha-Extension-Model#2390 remains open, ready and unmerged at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`; its complete paginated patch contains
only `.github/workflows/pr-00-gate.yml`, with exactly one addition/deletion
removing only `labeled`. Workflows#4503 remains open and ready. Current metadata
and consumer patch are in `campaign-reconciliation-round-5.json`. No duplicate
campaign PR was created. `~/.codex/bin/handoff.sh` is absent, so the handoff roster
cannot be independently inspected here.

Remaining: final campaign disposition, complete authenticated post-merge scanner
readback and all Gate runs in the ensuing 48 hours with pagination. The final
merge timestamp and exact observation completion time are undetermined while
#2390 remains unmerged. Numerator, denominator and percentage are uncollected;
no campaign completion or observation acceptance is claimed.

Full formatting verification: the required Black command with
`BLACK_NUM_WORKERS=1` hit the 55-second process timeout despite reporting 907
files unchanged. The same complete scope passed with exit 0 using the existing
sandbox event-loop workaround:

```bash
timeout 55s python -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Result: 907 files would be left unchanged. No formatting exclusions were added.
Staging the scoped test and evidence failed with exit 128 because creating
`.git/index.lock` is denied on the read-only filesystem. No commit or push was
possible. The connector rejected both the requested `needs-human` label and the
WF#4082 comment with `MCP tool call requires approval, but approval policy is never`.
`issue-comment-round-5.md` retains the prepared comment for an authorized parent;
no remote checklist update is claimed. Unrelated untracked files were untouched.
