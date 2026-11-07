# WF#4082 verification

Check date: 2026-11-06T22:45:01.133260+00:00

Before-edit outcome command (Health 68's existing scanner, bounded to 110 seconds):

```bash
repos_input=$(python scripts/list_registered_consumer_repos.py --separator=,)
timeout 110s python scripts/check_consumer_sync_drift.py --repos "$repos_input" --report-json /tmp/issue-4082-drift.json
```

Interpreter: `/opt/hostedtoolcache/Python/3.14.10/x64/bin/python` (Python 3.14, selected by Health 68).
Attempt/time stop rule: one live scan, 110-second hard limit; stop on unavailable
network/authentication rather than retrying or inferring equality. Do not repair
unrelated drift. Run associated tests once before changes and once after them.

Requested root `docs/AGENT_ISSUE_FORMAT.md` is absent. Inspected canonical
available copy `templates/consumer-repo/docs/AGENT_ISSUE_FORMAT.md` instead.
`~/.codex/bin/handoff.sh` is absent in this runner, so its SUPPORTED_REPOS cannot
be reconciled here. Registered discovery returns 16 consumers.

Root and template pull_request types are both `[opened, synchronize, reopened,
ready_for_review]`. Gate remains create_only, Template remains the sole overwrite
exception, and Manager-Database retains its custom-Gate skip with a reason.
No workflow or manifest edits are authorized or needed for this verification.

`gh pr view`/`gh pr diff` attempts failed: runner cannot reach api.github.com.
Connected GitHub reads are used for campaign disposition evidence separately;
these do not satisfy the required authenticated gh/Health 68 acceptance command.

## Verified work and remaining requirements

- [x] First task: inspected the available issue-format guide, root/template Gate
  triggers and compiled manifest protections. A new contract test checks that
  Gate resolves to the template, remains create-only, overwrites only Template,
  and preserves the Manager-Database skip and its reason.
- [x] Reconciled the 14 existing consumer PRs through authenticated connected
  `fetch_pr` and paginated `list_pr_changed_filenames` reads after the explicitly
  requested `gh` commands failed. Every consumer diff is exactly one addition
  and one deletion in `.github/workflows/pr-00-gate.yml`, removing only `labeled`.
  Current heads and merge timestamps are in `campaign-readback.json`.
- [ ] Lane-fleet discovery remains incomplete: this runner has no handoff.sh.
- [ ] Associated full test suite / authenticated Health 68 acceptance remains
  blocked by unavailable GitHub networking; no tests were disabled or skipped.
- [ ] Final campaign merge and the complete subsequent 48-hour observation.

Workflows#4084 merged at 2026-10-18T06:29:45Z; its implementation already
reports extra, missing, unreadable and malformed trigger lists. The bounded
real-input scan demonstrated an unhandled ConnectionError in read preflight.
Only that failure is repaired: repository and contents preflight requests now
record safe exception class diagnostics and feed the existing error-report path.
Both new regression cases failed with ConnectionError before the repair.

After the repair, the same scan finished in under one second, exit 1, with
`::error::No usable GitHub token available for consumer repo contents reads`.
The JSON report records repo_count=16, errors=1, selected_source empty, and
`repo preflight failed for stranske/Travel-Plan-Permission: request failed (ConnectionError)`.
The scan did not read consumer trees or establish trigger equality. Transport
exception messages and credential values are excluded from diagnostics.

Connected default-branch reads (fetch_file, lines 1-80) successfully exposed
inline trigger lists for all 15 eligible registered consumers: all four required
activity types and no extras. Manager-Database was excluded by manifest policy.
See file SHAs and collection timestamp in `campaign-readback.json`. These are
supplemental live reads, not an authenticated gh scan or a post-campaign claim.
No duplicate PRs or consumer workflow changes were made.

Thirteen campaign PRs are merged. Portable-Alpha-Extension-Model#2390 is open,
ready for review, head `09298cf6b2e719b90ad661ea62553f4504d5dd96`, and has the
intended one-line diff. Its default-branch trigger list also currently matches;
that does not prove this PR merged. The latest *completed* consumer merge is
Ready#633 at 2026-10-18T14:51:47Z. It is not the final campaign merge.
The final timestamp and exact observation completion time are therefore not yet
known. Numerator, denominator and percentage are uncollected, not zero, and no
48-hour acceptance claim is made.

Validation:

```bash
python -m pytest tests/scripts/test_check_consumer_sync_drift.py tests/workflows/test_gate_trigger_contract.py tests/workflows/test_consumer_sync_create_only_evidence.py -q -m 'not slow'
```

127 passed. The broader requested suite adds
`tests/workflows/test_health_68_liveness.py`: 135 passed, 1 failed. The sole
failure is `test_consumer_drift_detector_executed_recently`, whose live gh API
read cannot connect to api.github.com (also failed before these changes).
Ruff on all three changed Python files and `git diff --check` pass.
Each changed Python file was individually formatted and checked with Black,
line length 100; repository-wide formatting gate status is recorded below.

## Handoff blockers

Git staging failed with exit 128: `.git/index.lock` cannot be created because
`.git` is read-only. No commit or push was possible in this runner.
Authenticated GitHub reads succeeded through the connected tools, but both the
WF#4082 comment and needs-human label mutations were rejected with:
`MCP tool call requires approval, but approval policy is never`.
The exact prepared update is retained as `issue-comment.md`; WF#4082 was not
modified. No PR was created or changed. Workflows#4503 and the remaining open
consumer campaign PR #2390 were both verified open with draft=false.

The exact repository-wide Black command was attempted. Default parallel
execution failed because the sandbox rejects the multiprocessing forkserver's
socket bind; plain single-worker runs stalled awaiting event-loop notification.
The same Black CLI completed successfully using one worker and a periodic no-op
signal to wake its event loop. This changes no formatting checks or exclusions:

```bash
timeout 110s python -c 'import signal; signal.signal(signal.SIGALRM, lambda *_: None); signal.setitimer(signal.ITIMER_REAL, 0.2, 0.2); import black; black.patched_main()' --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' --workers 1 .
```

Exit 0: 907 files would be left unchanged. Each changed Python file was also
individually formatted and checked successfully with the ordinary Black CLI.
The remaining commit blocker is read-only `.git`.
