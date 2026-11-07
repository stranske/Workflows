# WF#4082 follow-up verification

Check date: 2026-11-06T23:07:32.384727+00:00

Before-code-edit real-input command:

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --summary /tmp/issue-4082-round2-summary.md --report-json /tmp/issue-4082-round2-drift.json
```

Interpreter: /opt/hostedtoolcache/Python/3.14.10/x64/bin/python, Python 3.14
as selected by Health 68. Stop rule: one live attempt before edits and one after,
each bounded to 110 seconds; stop on unavailable networking/authentication.
Repair only a failure demonstrated by this command. No workflow changes.

Recent commit aa9f8ef2 already added preflight exception handling and regression
tests. The first task's contract tests pass again: 40 passed. Authenticated
connected reads reverified all 14 current consumer PR heads and sole-file
one-line labeled removals. Thirteen are merged; Portable-Alpha-Extension-Model
2390 remains open, ready, head 09298cf6b2e719b90ad661ea62553f4504d5dd96.
The final campaign merge time and observation completion time remain unknown.
PR 4503 is open and ready. Its first checkbox update was rejected by the
connected tool: MCP tool call requires approval, but approval policy is never.
The reconciliation must be published by an authorized parent.

Before-edit outcome: exit 1 in 0.25 seconds. No usable GitHub read credential;
repo_count=16, errors=1.
The JSON contains no gate_triggers field, stdout has no per-consumer unknown
lines, and the requested summary file is absent. This is the scoped reporting
gap to repair: retain visible unknown Gate status for each in-scope consumer
when read preflight prevents the comparisons. Do not imply all-match.

Post-edit scan collected: 2026-11-06T23:10:06.912355+00:00.
Same command: exit 1 in 0.27 seconds, repo_count=16, errors=1, all 16 Gate
statuses unknown in stdout, JSON and the requested summary. No successful
consumer reads and no all-match claim. The retained drift-report-round-2.json
records the unavailable network diagnostics without credential values.
Manager-Database is skipped for file delivery but remains in the Gate FYI
comparison scope per the current maintenance contract (16, not 15, compared).

Both expanded preflight regression cases failed before the repair with
KeyError: gate_triggers. After the repair:

```bash
python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

127 passed in 4.50s, covering matching, extra, missing, failed and malformed
trigger reads, including custom-Gate reporting without overwrite authority.
Adding tests/workflows/test_health_68_liveness.py gives 135 passed, 1 failed
in 4.52s: test_consumer_drift_detector_executed_recently cannot connect to
api.github.com. No tests were disabled or skipped.
Ruff passes for both changed Python files; git diff --check passes.
The direct authenticated gh api read of Travel-Plan-Permission's Gate also
failed to connect, so post-campaign authenticated readback remains incomplete.

Fresh campaign evidence is retained in campaign-reconciliation-round-2.json:
14 current heads and paginated changed-file inventories; each diff has one
addition and one deletion, exactly removing labeled from the Gate types line.
Thirteen merged, one open/ready. No final campaign merge can be declared.
No run collection was substituted for the required post-final-merge interval;
numerator, denominator and percentage remain uncollected. The interval will
complete exactly 48 hours after the still-unknown final merge timestamp.

Prepared PR reconciliation (four verified checkboxes) is pr-body-round-2.md.
The original live PR was unchanged: metadata update and needs-human label
mutations were rejected because the connected tools require approval while
this run's approval policy is never. No workflow edits were made or required
for this scanner repair. Handoff roster discovery remains blocked by absent
~/.codex/bin/handoff.sh.

The exact repository-wide Black command was attempted and failed because the
sandbox rejects the multiprocessing forkserver socket bind. The ordinary
single-file formatting commands pass for both changed Python files. The same
repository-wide check completed with one worker and a periodic no-op signal to
wake the sandboxed event loop (no checks or exclusions changed):

```bash
timeout 110s python -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Exit 0: 907 files would be left unchanged. No formatting changes needed.
The source-issue comment mutation was also rejected by the connector's
never-approval policy; issue-comment-round-2.md retains the prepared message.

Commit handoff: git add of the two Python files, contract doc, and scoped evidence
failed with exit 128: .git/index.lock cannot be created (read-only file system).
No commit or push was possible. These working-tree changes require the
parent automation to stage and commit; unrelated untracked session/node_modules
files were left untouched. No PR was created or changed by this run.
