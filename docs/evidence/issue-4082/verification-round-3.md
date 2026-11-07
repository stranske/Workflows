# WF#4082 follow-up verification, round 3

Before-code-edit check date: 2026-11-06T23:29:56Z.
Interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (3.14.10),
the runner-selected Python used by Health 68.

Real-input outcome command:

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round3-summary.md --report-json /tmp/issue-4082-round3-drift.json
```

Attempt/time stop rule: one baseline attempt per authentication condition and
one post-edit attempt, each capped at 110 seconds; do not retry unavailable
networking. Repair only missing failure evidence demonstrated by these commands.
The first baseline returned 1 in 0.50 seconds, reporting all 16 registered
consumer Gates as unknown after read preflight failed. It establishes no equality.

Also exercise the same registered roster, manifest and template when no read
credential is available, without changing or printing any credential value:

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
env -u DRIFT_TOKEN -u SERVICE_BOT_PAT -u OWNER_PR_PAT -u ACTIONS_BOT_PAT -u AGENTS_AUTOMATION_PAT -u GITHUB_TOKEN -u GH_TOKEN timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round3-no-auth-summary.md --report-json /tmp/issue-4082-round3-no-auth-drift.json
```

Before-edit no-credential outcome: exit 1 in 0.13 seconds. The JSON had no
`gate_triggers` or `selected_source`, stdout contained only the authentication
error, and no summary was written. The expanded regression failed before the
repair (`KeyError: selected_source`; 1 failed, 2 passed). The repair routes this
case through the existing failed-preflight reporting path after local manifest
validation; it neither issues unauthenticated requests nor changes permissions.

Campaign discovery: the registry returns 16 consumers. The root issue-format
guide and `~/.codex/bin/handoff.sh` are absent; the available issue-format guide
is `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md`. Root and template Gate
types remain `[opened, synchronize, reopened, ready_for_review]`. The manifest
retains create-only delivery, the Template overwrite override, and the custom
Manager-Database skip. No protected workflows or delivery policy were changed.

Requested `gh pr view 4084` and `gh pr diff 4084` failed to connect to GitHub.
Connected reads of Workflows#4084 and Portable-Alpha-Extension-Model#2390
succeeded. The latter remains open and ready; a final campaign merge timestamp
and exact 48-hour observation completion time cannot yet be determined.
Do not treat unavailable run counts as zero or claim campaign completion.

Post-edit results:

- At 2026-11-06T23:31:49Z, the no-credential command returned 1 in 0.41 seconds;
  all 16 Gates were explicitly unknown in stdout, JSON and summary.
- At 2026-11-06T23:32:10Z, the normal command returned 1 in 0.39 seconds;
  all 16 Gates remained unknown because GitHub networking was unavailable.
- `drift-report-round-3.json` retains both reports' repository coverage, errors,
  Gate lines and safe read diagnostics. Neither command establishes live equality.
- `gh pr view` / `gh pr diff` for Portable-Alpha-Extension-Model#2390 and
  `gh api repos/stranske/Travel-Plan-Permission/contents/.github/workflows/pr-00-gate.yml --jq .sha`
  also failed to connect. Do not substitute the connected PR reads for the
  required complete post-merge authenticated scanner readback.

Validation command:

```bash
timeout 110s python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

128 passed in 6.00 seconds. Including `tests/workflows/test_health_68_liveness.py`
gave 136 passed, 1 failed in 6.33 seconds: the live execution probe could not
reach api.github.com. No tests were disabled or skipped. Ruff and
`git diff --check` passed. The change preserves the distinct existing missing
and unusable credential error messages and diagnostic codes.

Current connected PR metadata and the complete Portable-Alpha patch are in
`campaign-reconciliation-round-3.json`. The consumer patch remains exactly one
addition and one deletion removing only `labeled`; no duplicate PR was created.
Workflows#4503 and Portable-Alpha-Extension-Model#2390 remain open and ready.
The previous full 14-PR reconciliation remains in the round-2 artifact; this
round refreshed only the unresolved consumer and Workflows PRs.

The connector rejected both the WF#4082 comment and `needs-human` label:
`MCP tool call requires approval, but approval policy is never`.
`issue-comment-round-3.md` retains the prepared comment for an authorized parent.
No task checkbox was changed, and no campaign acceptance claim was made.

Black formatted both changed Python files at line length 100. The exact full
repository command was attempted but the sandbox blocked the multiprocessing
forkserver's socket bind. The identical check completed successfully using one
worker and a periodic no-op signal to wake its event loop:

```bash
timeout 110s python -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Exit 0: 907 files would be left unchanged. No checks or exclusions were removed.

Final regression recheck: 3 passed, 78 deselected; selection was restricted to
the changed preflight test, with no tests disabled. Staging the scoped source,
tests, contract doc and evidence failed with exit 128:
`.git/index.lock` cannot be created because `.git` is read-only. No commit or
push was possible. An authorized parent must stage and commit these changes;
unrelated untracked node_modules and session files were left untouched.
