# WF#4082 verification, round 4

Before-edit check: 2026-11-06T23:51:41.560780Z. Interpreter:
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (runner-selected Python 3.14).

Real-input outcome command, copied from Health 68's comparison step:

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round4/summary.md --report-json /tmp/issue-4082-round4/drift.json
```

Stop rule recorded before edits: one baseline and one post-test scan, each
capped at 110 seconds; do not retry unavailable networking or invent a runtime
repair. The baseline returned 1 with all 16 registered consumers explicitly
unknown. The post-test scan at 2026-11-06T23:52:52.735420Z returned 1 in 0.40648
seconds with the same outcome. `drift-outcome-round-4.json` records the exact
command, interpreter, roster, timestamps and Gate lines. No live consumer
read succeeded through the scanner; neither result establishes equality.

The new test, `test_registered_gate_cli_preserves_unknowns_without_read_access`,
runs the registry CLI followed by the actual scanner subprocess using the real
manifest, canary configuration and template. It removes read credentials from
the child environment and requires unknown Gate statuses for the entire
in-scope roster in stdout, JSON and the summary. It also requires an explicit
read failure and absence of `gate triggers: all match`. This extends the mocked
preflight regressions to the production CLI/configuration integration; it does
not simulate successful live readback or change scanner behavior.

Validation before the test change: 128 passed in 5.62 seconds. Afterward:

```bash
timeout 110s python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

129 passed in 6.18 seconds. Ruff and `git diff --check` passed. No existing
tests were disabled or skipped.

Inspection confirms root and template Gate types remain
`[opened, synchronize, reopened, ready_for_review]`; create-only delivery,
Template's overwrite override and Manager-Database's skip are unchanged.
`docs/AGENT_ISSUE_FORMAT.md` is absent; the existing guide is
`templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`, which was inspected.
`~/.codex/bin/handoff.sh` remains absent, preventing complete handoff-roster
discovery. No workflow or protected configuration was edited.

`gh pr view`, `gh pr diff` and the authenticated `gh api` Gate-content read
failed to connect to api.github.com. Connected GitHub reads confirm #4084
is merged and its existing implementation compares extra and missing triggers,
preserves custom-Gate visibility and prevents all-match on unreadable Gates.
Portable-Alpha-Extension-Model#2390 remains open, ready and unmerged at
`09298cf6b2e719b90ad661ea62553f4504d5dd96`. Its complete current diff still changes
exactly one line in the sole file `.github/workflows/pr-00-gate.yml`, removing
only `labeled`. Workflows#4503 is open and ready at
`16d543e7c7fd641df8f5dc75276a1f451d17cb10`. Current read metadata and the consumer
patch are retained in `campaign-reconciliation-round-4.json`; earlier complete
campaign reconciliation remains separate. No duplicate campaign PR was made.

Remaining acceptance: reconcile and complete the final campaign disposition,
perform complete authenticated post-merge scanner readback, then collect all
Gate runs in the ensuing 48 hours with pagination. The final merge time and
exact observation completion time are unknown while #2390 remains unmerged;
the cancellation numerator, denominator and percentage are uncollected.
No campaign completion or newly completed checkbox is claimed.

Black formatted the changed Python file at line length 100. The exact required
full-repository check failed before checking files because the sandbox denies
the multiprocessing forkserver socket bind. The equivalent full check passed
with one worker and a periodic no-op signal to wake the event loop:

```bash
timeout 110s python -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Exit 0: 907 files would be left unchanged. The formatting scope and exclusions
are unchanged. The connector rejected publication of both the WF#4082 comment
and `needs-human` label: `MCP tool call requires approval, but approval policy
is never`. `issue-comment-round-4.md` retains the prepared comment for an
authorized parent. No remote checklist was updated.

Commit attempt: staging the scoped test and evidence failed with exit 128
because `.git/index.lock` cannot be created on the read-only filesystem.
No commit or push was possible; an authorized parent must stage and commit
the prepared changes. Unrelated node_modules and session files were untouched.
