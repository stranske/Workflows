# Issue 4484 focused validation

Check date: 2026-11-06. Interpreter: /opt/anaconda3/bin/python3.

The concrete SubscriptionClient.invoke(prompt, **_kwargs) accepts config; the real implementation is exercised with only availability and the subprocess boundary mocked. No subscription CLI is launched.

## Deliberate break: _llm_client.py

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py::test_no_arg002_violations[_llm_client.py]`

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________________ test_no_arg002_violations[_llm_client.py] ___________________

filename = '_llm_client.py'

    @pytest.mark.parametrize("filename", ["_llm_client.py", "pr_verifier.py"])
    def test_no_arg002_violations(filename: str) -> None:
        """Check each copy-delivered source with the consumer's unused-argument rule."""
        source = ROOT / "scripts" / "langchain" / filename
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    
>       assert result.returncode == 0, result.stdout + result.stderr
E       AssertionError: ARG002 Unused method argument: `config`
E           --> scripts/langchain/_llm_client.py:40:35
E            |
E         38 |     client: Any
E         39 |
E         40 |     def invoke(self, prompt: Any, config: Any = None, **kwargs: Any) -> Any:
E            |                                   ^^^^^^
E         41 |         if not isinstance(prompt, str):
E         42 |             to_string = getattr(prompt, "to_string", None)
E            |
E         
E         Found 1 error.
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/opt/anaconda3/bin/python3', '-m', 'ruff', 'check', '--isolated', '--select', 'ARG002', '/User...e(prompt, str):\n42 |             to_string = getattr(prompt, "to_string", None)\n   |\n\nFound 1 error.\n', stderr='').returncode

tests/langchain/test_arg002_regression.py:29: AssertionError
=========================== short test summary info ============================
FAILED tests/langchain/test_arg002_regression.py::test_no_arg002_violations[_llm_client.py]
1 failed in 0.39s

Exit: 1
```

Restored the retained fix:

```text
.                                                                        [100%]
1 passed in 0.20s
Exit: 0
```

## Deliberate break: pr_verifier.py

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py::test_no_arg002_violations[pr_verifier.py]`

```text
F                                                                        [100%]
=================================== FAILURES ===================================
__________________ test_no_arg002_violations[pr_verifier.py] ___________________

filename = 'pr_verifier.py'

    @pytest.mark.parametrize("filename", ["_llm_client.py", "pr_verifier.py"])
    def test_no_arg002_violations(filename: str) -> None:
        """Check each copy-delivered source with the consumer's unused-argument rule."""
        source = ROOT / "scripts" / "langchain" / filename
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--isolated", "--select", "ARG002", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    
>       assert result.returncode == 0, result.stdout + result.stderr
E       AssertionError: ARG002 Unused method argument: `config`
E             --> scripts/langchain/pr_verifier.py:8735:35
E              |
E         8733 |         )
E         8734 |
E         8735 |     def invoke(self, prompt: str, config: Any = None, **_: Any) -> Any:
E              |                                   ^^^^^^
E         8736 |         import urllib.error
E         8737 |         import urllib.request
E              |
E         
E         Found 1 error.
E         
E       assert 1 == 0
E        +  where 1 = CompletedProcess(args=['/opt/anaconda3/bin/python3', '-m', 'ruff', 'check', '--isolated', '--select', 'ARG002', '/User...^^^^\n8736 |         import urllib.error\n8737 |         import urllib.request\n     |\n\nFound 1 error.\n', stderr='').returncode

tests/langchain/test_arg002_regression.py:29: AssertionError
=========================== short test summary info ============================
FAILED tests/langchain/test_arg002_regression.py::test_no_arg002_violations[pr_verifier.py]
1 failed in 0.31s

Exit: 1
```

Restored the retained fix:

```text
.                                                                        [100%]
1 passed in 0.23s
Exit: 0
```
## Final focused checks

`/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py tests/scripts/test_verifier_capacity_backup.py`

Printed `101 passed in 9.72s` on the first focused run.

`/opt/anaconda3/bin/python3 -m ruff check --isolated --select ARG002 scripts/langchain/_llm_client.py scripts/langchain/pr_verifier.py`

Printed `All checks passed!`.

The two exact template-parity tests that failed in run 42291331314 printed
`2 passed in 0.26s` after aligning the retained verifier suppression:

- `tests/scripts/test_pr_verifier_sync_manifest.py::test_pr_verifier_source_and_consumer_template_are_identical`
- `tests/scripts/test_native_capacity_registry.py::test_native_facts_and_helper_are_managed_with_exact_template_parity`

## First unresolved step

The ledger has unquoted colon-containing notes and unsupported `completed`
statuses. The session marks `.agents` read-only; writing the correction returned
`PermissionError: [Errno 1] Operation not permitted`. No bypass was attempted.
A proposed patch at `/tmp/4487-ledger-repair.patch` quotes note strings, changes
`completed` to `done`, and binds finished entries to retained substantive commit
`de5f440ac`. Validating its temporary copy with
`/opt/anaconda3/bin/python3 scripts/ledger_validate.py /tmp/issue-4484-ledger.yml`
printed `Validated /tmp/issue-4484-ledger.yml`. This is proposed-patch evidence,
not validation of the unchanged repository ledger.

Guarded source delivery remains blocked by ledger validation. Consumer lint on
an automatically regenerated PR and the next sync-core classification remain
unproven and must follow source delivery. The generated consumer PR was not edited.

## Consumer-template regression extension

The lint regression now checks the consumer-template verifier as well as both
copy-delivered source files. There is no separate `_llm_client.py` template;
the sync manifest delivers that file from the root source.

- [x] Extend the regression test and verify that reintroducing the unused
  `config` argument fails it, then restore the fix and verify it passes.

Each of `subscription-source`, `verifier-source`, and `verifier-template` in
`tests/langchain/test_arg002_regression.py::test_no_arg002_violations` failed
with `ARG002 Unused method argument: config` after deliberately removing its
fix. Each passed after restoration. No deliberate-break edits were retained.

On Python 3.14.10, this focused command passed with **124 passed in 3.13s**:

```bash
python -m pytest -q tests/langchain/test_arg002_regression.py tests/scripts/test_verifier_capacity_backup.py tests/scripts/test_pr_verifier_sync_manifest.py -m 'not slow'
```

Both the repository Ruff configuration and an isolated `--select ARG002` check
passed on the two source files and the verifier template. The repository check
also included the changed regression test.

A broader run including `tests/scripts/test_llm_client_shared.py` stalled after
43 tests and was interrupted; it is not recorded as passing. GitHub API access
failed, so PR readiness, regenerated consumer CI, and the next sync-core round
remain unverified. No consumer PR or workflow was changed.

Black formatting and its single-file check passed for the changed Python test.
The required repository-wide Black command failed when its default workers
could not bind the forkserver socket in the sandbox. A single-worker retry
stalled and was interrupted; a fork-mode diagnostic retry timed out after
45 seconds. The full formatting gate remains unverified.

Staging the two changed files failed with `Unable to create .git/index.lock:
Read-only file system`. No commit or push was made.

## Closer repair readback, 2026-11-06 (2026-11-07 UTC)

Operational outcome: the regenerated consumer's `Python CI / lint-ruff` succeeds
on its exact current head, and the next completed sync-core classification has
no issue-4484 shipment finding. This does not establish consumer merge or full
issue completion.

Proof command: `gh run view 42325500360 --repo stranske/Travel-Plan-Permission`.
Stop rule: three repair attempts or 75 minutes; each local check is bounded to
two minutes. No controller, regeneration, sync-core round, or consumer edit was
launched by this repair.

### Source and retained work

Read PR #4487's complete diff and all three current review threads through the
GitHub connector. It is merged at `dbc2f4d59575e74347462a129cead90eb9729aaf`;
`git merge-base --is-ancestor dbc2f4d59575e74347462a129cead90eb9729aaf origin/main`
returned 0. Current main and the provisioned `closer-r1/issue-4484` branch started
at `75d4c8360c7a31db51366ca08d736cf4be1bc894`.

`git branch --list 'closer*/issue-4484'` listed only `closer-r1/issue-4484`;
`git log --oneline origin/main..closer-r1/issue-4484` was empty. There was no
unmerged local repair to import. All of #4487 is retained, including the source
fix, verifier-template alignment, tests and mutation-receipt updates. Nothing
from that delivery was discarded or redone.

Inspected the complete `tests/langchain/test_arg002_regression.py` and
`tests/scripts/test_verifier_capacity_backup.py`. Config forwarding is asserted
by identity alongside prompt rendering and `stop`; the concrete
`tools.subscription_llm.SubscriptionClient.invoke(prompt, **_kwargs)` accepts
these options, while its real command/environment/result parsing runs with only
availability and `subprocess.run` mocked for Codex and Claude. The transport
assertions establish that config and stop do not reach subprocess keyword
arguments. The backup HTTP test asserts the complete posted model/messages
payload for all three config values, so config does not leak into the request.
No applicable source or test defect was found; no CLI or paid provider was run.

### All three review-thread dispositions

| Thread on #4487 | Current state | Disposition |
| --- | --- | --- |
| `PRRT_kwDOQprj9M60o6P2` ([comment 4496109024](https://github.com/stranske/Workflows/pull/4487#discussion_r4496109024)) | Resolved, outdated | Duplicate task-12/task-13 are already absent. Retain the resolution. |
| `PRRT_kwDOQprj9M60o6P6` ([comment 4496109032](https://github.com/stranske/Workflows/pull/4487#discussion_r4496109032)) | Resolved, outdated | task-09/task-11 are deferred; task-14/task-15/task-16 are absent. Local focused checks are recorded separately below. |
| `PRRT_kwDOQprj9M60o6P-` ([comment 4496109039](https://github.com/stranske/Workflows/pull/4487#discussion_r4496109039)) | Unresolved, outdated | Applicable ledger defect: consolidate fragment task-03 into task-02 and task-05 into task-04, retaining original commit/timestamp evidence. The normal patch was rejected because this session marks `.agents` read-only. Leave the thread unresolved until an authorized filesystem writer commits the correction. |

The current ledger already uses supported `done` statuses and quoted notes;
the earlier malformed-YAML observation above is historical, not a current claim.
The intended small consolidation changes only ledger titles, combined completion
intervals and preserved notes. It requires no new implementation task. Updating
task-09/task-11 receipts in `.agents/issue-4484-ledger.yml` is also unavailable in
this session. The managed patch tool returned exactly:

```text
patch rejected: writing outside of the project; rejected by user approval settings
```

No alternate write mechanism or permission bypass was attempted. The writable
validation document carries the actual receipts; the ledger remains unchanged.

### Local focused checks

On source head `75d4c8360c7a31db51366ca08d736cf4be1bc894`:

```bash
/opt/anaconda3/bin/python3 -m pytest -q tests/langchain/test_arg002_regression.py tests/scripts/test_verifier_capacity_backup.py tests/scripts/test_pr_verifier_sync_manifest.py -m 'not slow'
```

```text
........................................................................ [ 55%]
..........................................................               [100%]
130 passed in 12.16s
Exit: 0
```

```bash
/opt/anaconda3/bin/python3 -m ruff check --isolated --select ARG002 scripts/langchain/_llm_client.py scripts/langchain/pr_verifier.py templates/consumer-repo/scripts/langchain/pr_verifier.py
```

```text
All checks passed!
Exit: 0
```

The focused tests include the existing temporary deliberate-break and restored
checks for all three delivered paths. No mutation was retained.

### Exact consumer head and lint receipt

Read-only PR metadata reports #1716 open and ready for review at
`58dc10da4b4f7f11e283a9a49c34084b3e258f59` on `sync/workflows-candidate`.
Reading `_llm_client.py` at that immutable head confirms config forwarding.
The controller's Maint 71 receipt binds the same consumer head to source commit
`75d4c8360c7a31db51366ca08d736cf4be1bc894` and delivery generation `8a56dd3d8c6b`.

```bash
gh run view 42325500360 --repo stranske/Travel-Plan-Permission --json databaseId,headSha,status,conclusion,jobs,url --jq '{databaseId,headSha,status,conclusion,url,jobs:[.jobs[] | select(.name | contains("lint-ruff")) | {databaseId,name,status,conclusion,completedAt,url}]}'
```

```json
{"conclusion":"success","databaseId":42325500360,"headSha":"58dc10da4b4f7f11e283a9a49c34084b3e258f59","jobs":[{"completedAt":"2026-11-07T01:44:17Z","conclusion":"success","databaseId":128260118240,"name":"Python CI / lint-ruff","status":"completed","url":"https://github.com/stranske/Travel-Plan-Permission/actions/runs/42325500360/job/128260118240"}],"status":"completed","url":"https://github.com/stranske/Travel-Plan-Permission/actions/runs/42325500360"}
```

Exit 0. [Successful lint job](https://github.com/stranske/Travel-Plan-Permission/actions/runs/42325500360/job/128260118240).

### Next completed sync-core classification

Read the existing controller-owned receipts; no round was dispatched:

- `/Users/teacher/.codex/orchestrator/sync-core/rounds.jsonl`, line 446:
  round `20261107T014654Z`, completed receipt timestamp `2026-11-07T01:47:11Z`.
- `/Users/teacher/.codex/orchestrator/sync-core/targets/stranske_travel_plan_permission_1716.json`:
  `head=58dc10da4b4f7f11e283a9a49c34084b3e258f59`,
  `last_round=20261107T014654Z`, `disposition=waiting`, `owner=ci`, `terminal=null`.
- `/Users/teacher/.codex/orchestrator/sync-core/scratch/m71/42325528409/sync-pr-merge-report.json`:
  same exact head and source commit, `delivery_disposition=awaiting-sealed-gate`,
  `status=delivery_sealed_checks_pending`, zero active review findings, and Gate
  rerun binding `run_id=42325500360`.

The prior completed round `20261107T012958Z` still had the shipment finding.
The next completed round, `20261107T014654Z`, records this target as:

```json
{"disposition":"waiting","error":null,"handoffs":[],"owner":"ci","reasons":["maint71: delivery_sealed_checks_pending; next=rerun-after-generated-delivery-seal-gate; refresh_reason=None"],"target":"stranske/Travel-Plan-Permission#1716"}
```

Thus the requested finding is absent in the next completed classification for
the regenerated head. `waiting` is not a merge receipt. The controller retains
ownership of its next Gate readback and delivery continuation. Blocking/drainable
pair at that observation: generated-delivery Gate pending / controller re-reads
completed Gate run 42325500360 on the same head.

### Documented repository test command (separate outcome)

`docs/CONTRIBUTING.md`, Python Tests, documents
`python -m pytest tests/workflows/ -v`. Ran that command with the required
interpreter, `/opt/anaconda3/bin/python3 -m pytest tests/workflows/ -v`, under
`subprocess.run(..., timeout=120)`. This is the documented workflow-test subset;
the repository-wide suite and release/verify pipelines were not run.

The captured log `/tmp/issue-4484-documented-tests.log` starts at
`2026-11-07T01:51:52Z`, reports Python 3.12.2 / pytest 9.1.1, and collected
3,534 tests. It ends at 36%, last updated `2026-11-07T01:53:50Z`, in
`tests/workflows/test_autofix_full_pipeline.py::test_autofix_pipeline_resolves_lint_and_typing`.
The 120-second wrapper did not produce a completed pytest summary; the child
exit status was not recovered from the original tool session. Outcome remains
UNKNOWN, not PASS. No retry, full-suite substitution or unrelated fix was made.

The third changed test in #4487,
`tests/docs/test_issue_4426_mutation_receipts.py`, was also read completely;
its diff updates the retained verifier digest. It is preserved unchanged.

### Remaining criteria

- [ ] Account for all three review threads and resolve applicable findings:
  all dispositions recorded, but ledger consolidation is still blocked by the
  session's read-only `.agents` policy.
- [x] Record passing focused local checks and exact-head consumer lint-ruff.
- [x] Record the next completed sync-core classification without this finding.
- [ ] Establish a passing documented repository test command: bounded run
  incomplete; no passing result claimed.

The ledger correction and documented test completion remain unresolved. The
source fix is retained and the live lint/classification outcomes are verified.
