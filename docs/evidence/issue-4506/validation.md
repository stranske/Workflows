# Issue #4506 delivery verification — 2026-11-07

## Canary dispatch with lagging general history

Reviewed recent commits through `f8be0d53`. No new operational checkbox is
verified complete. Fresh connected reads still show trip-planner #1957 open
and ready at `7ca6deb8d219fe9137fcb220de745e063f42c51c`. Native mypy job
`128338642025` retains the exact-head checkout and successful 484-file result.
The required literal `gh run view 42350906876 --repo stranske/trip-planner
--log` still exits 1 because this runner cannot connect to `api.github.com`.

Added a regression exercising `dispatchCanaryRefresh` through its native
inventory reader, decision, and dispatch path without injecting a precomputed
refresh state. For both a canary and a promotion producer on another source,
an empty general-history response must preserve the separately observed live
writer and prevent dispatch. Only a later empty native active-state inventory
permits one non-forced request pinned to the selected source. All remote calls
use inert doubles; these results do not establish live regeneration.

Validation: the dispatch suite passed **51 tests** (baseline: 50), the scoped
refresh suite passed **86 tests**, and `git diff --check` passed. Python 3.14.10
with mypy 2.4.1 ran the named two-file pytest command with `-m 'not slow'`:
**351 passed in 8.87s**, no skips. No Python or workflow files changed.

Source #4485 still provides only the older sync-core handoff for round
`20261107T011939Z`, evaluated head prefix `7f96a095cbd6`; source #4506 and
consumer #1957 comments provide no later classification. Both documented
controller-local receipt paths remain absent. The available connector has no
workflow-dispatch operation. A connected controller must perform the requested
regeneration and retain the next classification with its full evaluated head.

Attempts to correct the unsupported checked literal-gh items, add `needs-human`,
and post the concrete blocker comment each failed with `MCP tool call requires
approval, but approval policy is never`. No remote reconciliation succeeded.

Staging the tested JavaScript and evidence failed with `.git/index.lock:
Read-only file system`; no commit or push was possible. The verified change
remains in the working tree for a writer-capable continuation. Final connected
reads verified both Workflows #4530 and trip-planner #1957 open and ready.

## Multiple-writer completion regression

Reviewed recent commits `71509a7b`, `b6120277`, `42d89fd5`, and `73d3b51d`.
They establish local regressions, not fresh operational receipts. No additional
task is verified complete. Attempting to uncheck the unsupported literal-`gh`
task and acceptance criterion on PR #4530 was rejected with
`MCP tool call requires approval, but approval policy is never`.

Added a behavioral case to `tests/scripts/test_maint71_promote_dispatch.js`
that observes two old-source producers in different active states. Completing
one producer must leave refresh held while the other remains active. Only
observing both terminal allows one non-forced dispatch preserving the selected
evidence payload. The test uses inert API doubles and checks that the controller
does not mutate either writer observation.

Validation: the dispatch suite passed **50 tests**, scoped-refresh suite passed
**86 tests**, and `git diff --check` passed. With installed mypy 2.4.1, the selected
Python interpreter ran the named two-file pytest command with `-m 'not slow'`:
**351 passed in 10.83s, no skips**. No Python or workflow files changed.

Fresh connector reads still show consumer head
`7ca6deb8d219fe9137fcb220de745e063f42c51c` and both PRs open and ready.
Native mypy job `128338642025` still binds success to that head. The literal
`gh run view 42350906876 --repo stranske/trip-planner --log` again exited 1
with `error connecting to api.github.com`. The available source/consumer
comments contain no later sync-core receipt, and neither documented controller
receipt directory exists here. No producer was dispatched or live lock changed.

Git staging failed with `.git/index.lock: Read-only file system`, so no commit
was possible. Attempts to add `needs-human` and post the concrete blocker
comment were each rejected by the same MCP approval policy. Capacity mode is
`local-only` for writes. A writer-capable continuation must commit the tested
change and reconcile the remote checklist; the controller owner must retain
the requested regeneration and exact-head sync-core classification receipts.

## Writer-inventory transport failure verification

Added a regression case to `tests/scripts/test_maint71_promote_dispatch.js`
covering native API failures while collecting each of the five active writer
states. HTTP 403, 429, and 503 failures must propagate even after earlier state
queries returned empty inventories. The controller must stop before promotion
history or dispatch and cannot emit a dispatch receipt. All API calls in this
test use inert local doubles; it does not release live locks or start a writer.

`node tests/scripts/test_maint71_promote_dispatch.js` passed **49 tests, zero
skips**; the pre-change baseline passed 48. `git diff --check` passed. No Python
or workflow files changed.

Fresh connector reads still show trip-planner #1957 at
`7ca6deb8d219fe9137fcb220de745e063f42c51c` and both it and Workflows #4530
open and ready. Source #4485/#4506 and consumer #1957 comments provide no newer
sync-core classification for that head; the two documented controller receipt
paths remain absent. The literal `gh run view 42350906876 --repo
stranske/trip-planner --log` again exited 1 with `error connecting to
api.github.com`. No regeneration or sync-core acceptance is established, and
no additional task is complete. The remote checked literal-gh items remain
unsupported by this runner's evidence.

Staging the tested change failed with `.git/index.lock: Read-only file system`,
so no commit was created. Attempts to add `needs-human` and post the concrete
blocker comment on PR #4530 were both rejected with `MCP tool call requires
approval, but approval policy is never`; neither remote update succeeded.

The fix is present in the captured consumer head and its mypy CI passed.
Operational acceptance remains incomplete. Maint 68 run 42376854357 proves
a matching delivered tree, but does not classify sync-core findings. Native
mypy evidence was re-read through the GitHub connector; the literal `gh`
command still fails to connect. The unsupported completion claims from
the previous continuation have been removed from this record and the JSON
observation.

## Retained delivery

Read [trip-planner PR #1957](https://github.com/stranske/trip-planner/pull/1957)
through the GitHub connector. It is open and ready (`draft=false`) at
`7ca6deb8d219fe9137fcb220de745e063f42c51c`.

The immutable [delivered module](https://github.com/stranske/trip-planner/blob/7ca6deb8d219fe9137fcb220de745e063f42c51c/tools/llm_registry.py)
has Git blob ID `c43f6ef1252c817a03afd6efab9c7c6ee3e69a5e`.
Its `_load_positional_slots` rejects `provider is None` before either
`SlotDefinition` construction. Its complete bytes are retained at
`tests/fixtures/issue_4506/llm_registry.py.txt`, with the observation and
selected native log lines in `delivery-observation.json` alongside it.

The existing [Maint 68 run 42376854357](https://github.com/stranske/Workflows/actions/runs/42376854357)
completed its trip-planner job `128416416561` successfully. The native log says:

```text
2026-11-07T13:26:46.3624164Z Existing PR #1957 already matches this base and desired tree; preserving its review lifecycle while refreshing metadata
```

This is an existing controller receipt, not a regeneration dispatched by this
agent. No live writer lock was changed or additional writer started. The
workflow and consumer branch were not edited. The current delivery record
names source `37e230009cdba04743376410c9f72356b85fb64f`, sealed head
`7ca6deb8d219fe9137fcb220de745e063f42c51c`, and plan
`sha256:2adb36fccf3de39dcb595b9b53dba339d37c898f12769f95902a59ebfb585f1c`.

## Validation

The selected interpreter is
`/opt/hostedtoolcache/Python/3.14.10/x64/bin/python`, consistent with
`CI_PYTHON_VERSION=3.14`. Installed pytest is 9.2.0 and mypy is 2.4.1.
Ran the named command using that interpreter:

```sh
python -m pytest -q -o addopts= tests/test_llm_registry_malformed_input.py tests/workflows/test_delivered_scripts_mypy_clean_in_consumers.py
```

Result: **223 passed in 9.11s, no skips**, exit 0; stdout is retained in
`pytest.log`. The test change adds the captured consumer module to the existing
isolated consumer-layout mypy cases. Its fixed case succeeds; its pre-fix case
removes only the early guard and verifies the original `str | None` argument
error. A separate integrity test checks the captured bytes against GitHub's
observed blob ID. These tests do not query GitHub or mutate the consumer.

The connector independently read [CI run 42350906876](https://github.com/stranske/trip-planner/actions/runs/42350906876)
and its successful [Python CI / typecheck-mypy job 128338642025](https://github.com/stranske/trip-planner/actions/runs/42350906876/job/128338642025).
The log binds the checkout to a merge of the exact observed head:

```text
2026-11-07T07:21:08.5262937Z HEAD is now at 4b5133a Merge 7ca6deb8d219fe9137fcb220de745e063f42c51c into f9541643d8f6c7e9f4c431f615e78d284bf8081f
2026-11-07T07:21:33.0916086Z Success: no issues found in 484 source files
2026-11-07T07:21:33.1564223Z   MYPY_OUTCOME: success
```

The remote job installed mypy 2.4.0; the local consumer-layout checks used 2.4.1.
Both the native Mypy step and finalization step report success. These are
connector-fetched observations, not successful `gh` execution. The required
literal command was attempted and failed with exit 1:

```text
gh run view 42350906876 --repo stranske/trip-planner --log
error connecting to api.github.com
check your internet connection or https://githubstatus.com
```

## Remaining blockers and task accounting

- [ ] Execute regeneration through the controller-owned Maint 68 path. An
  existing successful matching-head receipt was retained; no new dispatch was
  made from this runner. The connector has no workflow-dispatch capability,
  local `gh` cannot connect, and controller-local state is absent.
- [x] Inspect the delivered provider guard at the immutable consumer head.
- [x] Run and retain the named pytest result.
- [ ] Read the consumer CI logs with the literal `gh run view ... --log` command.
  Equivalent native job evidence was retrieved through the connector, but the
  command-specific requirement remains unverified.
- [ ] Retain the next sync-core receipt evaluating the regenerated head.
- [x] Named pytest acceptance: mypy installed, consumer-layout cases executed.
- [ ] Literal `gh`-log acceptance.
- [ ] Sync-core clearance acceptance.

The controller-local paths documented by other source receipts,
`/Users/teacher/.codex/orchestrator/sync-core/rounds.jsonl` and the equivalent
runner-home path, do not exist here. The source issue #4485 comments contain
only older still-present handoffs; the latest retained one is
[round 20261107T011939Z](https://github.com/stranske/Workflows/issues/4485#issuecomment-6700244368)
on head prefix `7f96a095cbd6`. No current-head clearance is inferred from an
absence of later comments. The owner/controller must retain the round receipt
and exact evaluated head before marking that acceptance complete.

The edited test passes focused Black (line length 100), Ruff and `git diff --check`.
The mandatory repository-wide command
`black --check --line-length 100 --exclude '(\.workflows-lib|node_modules)' .`
failed with forkserver socket `PermissionError: Operation not permitted`.
A `BLACK_NUM_WORKERS=1` retry returned no terminal result and was interrupted
(exit 130). No repository-wide formatting pass or commit is claimed.

Staging the verified changes failed:
`fatal: Unable to create '.git/index.lock': Read-only file system`.
The runner mounts `.git` read-only, so the requested meaningful commit must
be made by a writer-capable continuation after its global Black gate passes.

The attempts to add `needs-human` and publish a blocker comment on Workflows
PR #4530 were both rejected with
`MCP tool call requires approval, but approval policy is never`.
No remote checklist, comment or label change succeeded. Both PR #4530 and
trip-planner #1957 were verified open and ready for review (`draft=false`).

## Consumer behavioral verification continuation

Re-read PR #1957 through the connected GitHub app: it is still open and ready
at `7ca6deb8d219fe9137fcb220de745e063f42c51c`. Fetching
`tools/llm_registry.py` at that immutable head again returned Git blob
`c43f6ef1252c817a03afd6efab9c7c6ee3e69a5e`, matching the retained capture.
The connected app again reported successful mypy job `128338642025` in
CI run `42350906876`; its log still binds the checkout to this exact head.

Extended the existing `slot_registry` fixture in
`tests/test_llm_registry_malformed_input.py` to import a temporary Python copy
of the retained consumer module. This executes the same 97 behavioral cases
against the delivered bytes, including malformed providers and retirement
history, valid neighboring slots, numbered overrides and fail-closed allowlists.
The capture itself is unchanged. The source and template cases still execute.

The named two-file pytest suite, with `-m 'not slow'`, passed **320 tests in
8.60s, no skips**, using Python 3.14.10 and installed mypy 2.4.1.
The command and stdout are retained in `pytest-consumer-behavior.txt`.
Focused Black (line length 100), Ruff and `git diff --check` passed.
The required repository-wide Black command failed with forkserver socket
`PermissionError: Operation not permitted`. A single-worker retry timed out
after 45 seconds (exit 124), reporting 521 files unchanged before aborting;
this is not a complete formatting pass. No commit or push was attempted
after that failed formatting gate.

The literal `gh run view 42350906876 --repo stranske/trip-planner --log`
again failed to connect to `api.github.com`. No next-head sync-core receipt
was available in PR #1957 or source-issue #4485/#4506 comments. No new
regeneration was dispatched, and no writer lock or consumer branch was changed.
These operational tasks remain unchecked.

Staging the test change again failed with `.git/index.lock: Read-only file
system`; no commit was created. The attempts to label PR #4530 `needs-human`
and post the blocker comment were both rejected with
`MCP tool call requires approval, but approval policy is never`.
No remote checklist, comment or label change succeeded.
Final connected-app reads confirmed PR #4530 and trip-planner #1957 remain
open and ready (`draft=false`).

## Retained CI receipt validation continuation

Re-read PR #1957 and native mypy job `128338642025` through the GitHub
connector. The PR remains open and ready at
`7ca6deb8d219fe9137fcb220de745e063f42c51c`. The native checkout and success
lines still match the retained observation. The literal required `gh run view
42350906876 --repo stranske/trip-planner --log` failed again with exit 1 and
`error connecting to api.github.com`.

Added `test_retained_consumer_mypy_receipt_passed_for_the_delivered_head` to
the named consumer-layout test file. It checks the native checkout's full head,
the job and both mypy step conclusions, and the successful typecheck and
`MYPY_OUTCOME` log lines. This prevents an old green checkout or skipped check
from silently establishing delivery acceptance. It validates retained evidence;
it does not establish a new controller dispatch or sync-core classification.

The named two-file suite passed **321 tests in 7.69s, no skips**, using the
selected Python 3.14.10 interpreter and installed mypy 2.4.1:

```sh
python -m pytest -q -o addopts= tests/test_llm_registry_malformed_input.py tests/workflows/test_delivered_scripts_mypy_clean_in_consumers.py -m 'not slow'
```

Deliberate receipt corruptions in temporary copies were all rejected: a changed
delivery head, a skipped mypy step, failed finalization, and missing final
success log. The unchanged native receipt passed. Focused Black (line length
100), Ruff and `git diff --check` passed.

Source-issue #4485/#4506 comments still contain no newer sync-core receipt for
this delivered head. No workflow-dispatch tool or controller-local state is
available; no regeneration was dispatched and no writer locks were changed.
All remaining operational tasks stay unchecked.

Adding `needs-human` and publishing the blocker comment on PR #4530 were
each rejected with `MCP tool call requires approval, but approval policy is
never`. Neither remote mutation succeeded. PR #4530 was also verified open
and ready (`draft=false`).

The required repository-wide Black check failed with the same multiprocessing
socket `PermissionError`. The `BLACK_NUM_WORKERS=1` retry returned no terminal
result and was interrupted (exit 130); no complete formatting pass is claimed.
Focused formatting was rechecked successfully. Git metadata reports unwritable
(`os.access('.git', os.W_OK)` is false). No commit or push was attempted after
the failed global formatting gate. The test and these notes remain uncommitted
for the automation writer to retain.

## Automated rejection checks and task reconciliation

Reviewed commits `80c8a5f6`, `6744efe3`, and `99856b77`. They verify the
captured provider guard and named pytest suite. They do not establish a new
controller dispatch, a successful literal `gh` log read, or the next sync-core
classification. The remote PR incorrectly checks the literal `gh` acceptance
criterion while leaving its corresponding task unchecked. Attempted to uncheck
that acceptance criterion; the connector rejected the update with
`MCP tool call requires approval, but approval policy is never`. The verified
task accounting in this document remains unchanged.

Fresh connector reads still show consumer PR #1957 open and ready at
`7ca6deb8d219fe9137fcb220de745e063f42c51c`. Native job `128338642025` in run
`42350906876` still reports completed/success, both mypy steps succeeded, and
its checkout and success log lines match the retained observation. The required
literal `gh run view 42350906876 --repo stranske/trip-planner --log` again
failed to connect to `api.github.com`. Source issue #4485's latest available
sync-core handoff remains round `20261107T011939Z` on older head `7f96a095cbd6`;
PR #1957 and issue #4506 provide no newer sync-core handoff. Neither the
controller's documented local receipt path nor its runner-home equivalent
exists here. This absence does not establish clearance.

Converted the previously manual receipt-corruption checks into ten executable
cases in the named consumer-layout test file. They reject a stale checkout,
another job, unfinished or failed jobs, skipped or unstarted mypy, failed
finalization, and missing checkout/typecheck/final-outcome log evidence. The
unchanged native receipt still passes. These tests validate retained evidence;
they do not substitute for the required operational receipts.

The named two-file suite passed **331 tests in 5.79s, no skips**, with Python
3.14.10 and installed mypy 2.4.1. Its command and output are retained in
`pytest-consumer-behavior.txt`. Focused Black, Ruff, and `git diff --check`
passed. No workflow, consumer branch, or live writer lock was changed.

Attempts to add `needs-human` and publish the reconciliation/blocker comment
were also rejected by the same approval-policy restriction. The controller
owner must retain the next classification receipt and its evaluated head,
and a connected authorized runner must perform the literal `gh` log read.

The mandatory repository-wide Black command was run with
`BLACK_NUM_WORKERS=1`; it produced no terminal result and was interrupted
(exit 130). This is not a formatting pass. Git metadata is still read-only
(`os.access('.git', os.W_OK)` is false). No commit or push was attempted;
the source-test change and updated evidence remain in the working tree for
the automation writer. Final connector reads verified Workflows PR #4530
and consumer PR #1957 are both open and ready (`draft=false`).

## Receipt reconciliation and named corruption cases — 2026-11-07

The preceding continuation incorrectly treated Maint 68's matching-tree receipt
as a sync-core classification and relabeled connector log excerpts as successful
literal `gh` output. Neither conclusion is supported by the native evidence.
Removed those claims and restored `gh_log_command.exit_code=1`,
`sync_core.status=unavailable`, and `sync_core.receipt=null` in the observation.

Fresh connected reads verified that consumer PR #1957 is still open and ready
at `7ca6deb8d219fe9137fcb220de745e063f42c51c`. Maint 68 run `42376854357` still
shows a successful trip-planner job and the matching-base/tree message retained
above. The native mypy job `128338642025` still contains the exact-head checkout,
484-file success, and `MYPY_OUTCOME: success` lines above. These receipts prove
delivery and native CI only. The available connector cannot dispatch workflows;
this runner cannot reach GitHub with `gh`, and has no controller-local state.
No workflow, consumer branch, or live writer lock was changed.

Source issue #4485's latest available sync-core handoff remains
[round 20261107T011939Z](https://github.com/stranske/Workflows/issues/4485#issuecomment-6700244368)
on older head prefix `7f96a095cbd6`. Follow-up issue #4506 and consumer PR #1957
provide no newer classification receipt. This does not establish clearance for
the captured consumer head; the controller owner must retain its next round.

The receipt-corruption tests now resolve mutation targets by native step name
and log marker, assert a valid baseline and unique target before entering
`pytest.raises`, and run every corruption against both original and reversed
steps/logs. Removing either required step now checks its specific missing-name
message. This directly exercises the reordered corruptions that the prior
standalone target-presence tests did not test.

Baseline: **340 passed in 11.30s, no skips**. After the change:

```sh
python -m pytest -q -o addopts= tests/test_llm_registry_malformed_input.py tests/workflows/test_delivered_scripts_mypy_clean_in_consumers.py -m 'not slow'
```

**351 passed in 11.13s, no skips**, exit 0, using Python 3.14.10 with mypy 2.4.1.
Focused Black, Ruff, and `git diff --check` passed. Regeneration, literal `gh`
log retrieval, and sync-core acceptance remain unchecked.

The repository-wide Black command failed with forkserver socket
`PermissionError: [Errno 1] Operation not permitted`. The single-worker attempt
produced no terminal result and was interrupted (exit 130). This is not a global
formatting pass. No commit or push was attempted: the required formatting gate
did not pass, and `.git` is read-only. The tested source change remains local.

Attempts to uncheck the unsupported literal-`gh` acceptance claim on PR #4530,
add `needs-human`, and post the blocker comment were each rejected with
`MCP tool call requires approval, but approval policy is never`. The PR body
therefore still contains that unsupported checked criterion; it needs correction
by an authorized writer. Final connector reads verified Workflows PR #4530 and
consumer PR #1957 are both open and ready (`draft=false`). The full latest pytest
result is appended to `pytest-consumer-behavior.txt`.

## Controller writer preservation regression — 2026-11-07

Added ten behavioral cases to `tests/scripts/test_maint71_promote_dispatch.js`
for the first unchecked task's live-writer preservation requirement. The actual
canary refresh decision and dispatch helpers must refuse a second writer in
each of `queued`, `in_progress`, `waiting`, `pending`, and `requested`, for
both canary and promotion producers from another source/plan. Their timestamps
exceed the retry debounce window. The tests verify zero dispatches and unchanged
writer observations while held. After observing a terminal cancelled run, they
verify exactly one non-forced Maint 68 request pinned to the requested source.
All API writes in these tests use the existing inert recorder.

`node tests/scripts/test_maint71_promote_dispatch.js`: **46 passed, no skips**
(36 existing plus 10 new). The selected Python interpreter's named two-file
pytest command with `-m 'not slow'` also passed **351 tests in 7.84s, no skips**;
mypy 2.4.1 is installed. `git diff --check` passed. No Python files changed.

Fresh connected reads still show consumer head
`7ca6deb8d219fe9137fcb220de745e063f42c51c` open and ready. Native mypy job
`128338642025` remains successful with that full head in its checkout log.
The literal `gh run view 42350906876 --repo stranske/trip-planner --log`
again failed to connect. The latest available sync-core handoff is still
round `20261107T011939Z` on older head prefix `7f96a095cbd6`; neither documented
controller-local receipt path exists here. No live writer or consumer branch
was changed, no controller dispatch was made, and no additional checkbox is
complete. Regeneration and next-head sync-core classification remain blocked
on a connected controller owner.

Staging these two files failed with `.git/index.lock: Read-only file system`;
no commit or push was possible. Attempts to add `needs-human` and publish the
blocker comment were each rejected with `MCP tool call requires approval, but
approval policy is never`. Neither remote mutation succeeded. Final connected
reads verified Workflows PR #4530 and consumer PR #1957 are open and ready
(`draft=false`). The tested JavaScript change and this record remain local.

## Native writer inventory verification continuation

Reviewed commits `42d89fd5`, `73d3b51d`, and `667a2312`. They do not establish
a fresh controller regeneration or next-head sync-core classification. A fresh
`gh run view 42350906876 --repo stranske/trip-planner --log` attempt still
exits 1 with `error connecting to api.github.com`. The remote PR nevertheless
checks that literal-command task and acceptance criterion. Attempting to
uncheck them was rejected: `MCP tool call requires approval, but approval policy
is never`. No checklist change succeeded; no additional task is complete.

Added two tests to `tests/scripts/test_maint71_promote_dispatch.js` exercising
the actual delivery refresh helper's native writer inventory collection.
Every active state must be queried without a source-SHA filter, and an
old-source, old-plan promotion must prevent dispatch even beyond the debounce
window. Missing, malformed, and saturated inventories must fail closed before
promotion history or dispatch. These extend the earlier pure-decision cases;
all remote writes in the tests use inert recorders.

Validation: `node tests/scripts/test_maint71_promote_dispatch.js` passed
**48 tests**; `node .github/scripts/__tests__/scoped-canary-refresh.test.js`
passed **86 tests**. The selected Python 3.14.10 interpreter ran the named
two-file pytest command with `-m 'not slow'`: **351 passed in 10.81s**, no
skips, with mypy 2.4.1 installed. `git diff --check` passed. No Python changed.

Fresh connected reads show PR #4530 and consumer PR #1957 open and ready;
the consumer head remains `7ca6deb8d219fe9137fcb220de745e063f42c51c`.
Available source #4485/#4506 and consumer comments contain no next-head
sync-core classification receipt. No controller dispatch or live writer
mutation occurred. Regeneration and sync-core acceptance remain incomplete.

Staging the JavaScript test failed with `.git/index.lock: Read-only file system`;
no commit or push was possible. The `needs-human` label and blocker comment
were also rejected with the same MCP approval-policy error. A writer-capable
continuation must commit the verified change; the controller owner must retain
the remaining operational receipts and correct the remote checklist.
