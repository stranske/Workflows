# Issue #4365: handoff regression verification

## Delayed continuation acceptance check — 2026-11-08

Before this round's test edits, ran:

```sh
timeout 60s node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js .github/scripts/__tests__/auto-pilot-handoff-lifecycle.test.js
```

Baseline: **101 passed, 0 failed**. Stop rule: one baseline and one post-edit
attempt, each limited to 60 seconds; investigate any named failure before one
corrective rerun. Full gates have one 180-second attempt each; timeout remains
incomplete. Expected additional observation: after an old handoff schedules
`done`, reopening and closing with a different PR must make that delayed
continuation refuse completion, preserve `agents:auto-pilot`, and require
`verify` for the new PR. A fresh successful handoff must then complete normally.

Rechecked GitHub metadata: #4447 and #4451 remain closed and unmerged; #4538 is
open with `draft=false`. Local `origin/main` includes the replacement contract
from #4463 (`7ab99d09`) and the explicit verifier-mode guard from #4537
(`c2ac6f38`). The prior helper/tests are preserved as regressions; no superseded
completion shortcut or workflow change is required for this test extension.

Results after adding six source/template cases:

- [x] The acceptance command above reports **107 passed, 0 failed**, including
  after restoring both helper files from temporary mutations.
- [x] New cases execute the actual verifier, continuation, and completion steps.
  They reject delayed completion when the closing PR changes, the head changes,
  or both change; ownership survives refusal and a fresh handoff completes.
- [x] Restoring label-only closed-state selection separately in each helper
  makes `issue 4365: delayed done after reopening rejects a different PR and
  head` fail. Restoring lost continuation (`verify` redispatches `auto`) also
  fails that named test separately on each surface. All four experiments exit 1;
  the corresponding three cases fail and the other surface's three pass.
  `git diff --exit-code` on both helpers confirms no mutation remains.
- [x] `timeout 60s python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -m 'not slow'`:
  **66 passed**, Python 3.14.10, with normal plugin loading.
- [ ] Full Node gate: `timeout 180s node --test .github/scripts/__tests__/*.test.js`
  exits **124**, summary **115 passed, 6 failed, 20 cancelled**. The two initially
  failing files, `agents-verifier-context.test.js` and
  `generated-delivery-seal-action.test.js`, report **199 passed, 18 failed** in a
  focused diagnostic run, including child-process `EPERM` and missing
  `delivery_not_sealed:staging`. No unrelated tests were changed or disabled.
- [ ] Full Python gate: `timeout 180s python3 -m pytest -q tests/ -m 'not slow'`
  exits **124**, progress about 2%, without a final summary.
- [ ] Commit: staging the JavaScript test and this evidence file fails with
  `.git/index.lock: Read-only file system`. The changes remain uncommitted.

Fresh live inspection found [Maint 71 run 42438994831](https://github.com/stranske/Workflows/actions/runs/42438994831)
reporting consumer #2454 at the same generated head
`b36b8ebf242bde649f6e31edc2cc915ad49d7421`, source
`c2ac6f38d6f2ce73f000158fa6f729bfece82092`, generation `4017589cec3c`.
The head-bound report has `review_state=clear`, `raw_active_count=0`,
`findings=[]`, and `status=campaign_prepared`; its `review_reassessment` job was
skipped. Both original threads remain outdated and unresolved. Issue #4365's
last sync-core bump still identifies `d6f4831035dd` / `20261106T115526Z`.
This adds current operational evidence but does not establish explicit
reassessment or live acceptance of the original findings. No workflow edit or
consumer branch modification was required or performed.

The PR #4538 checklist update, `needs-human` label, and results/blocker comment
were each rejected with `MCP tool call requires approval, but approval policy is
never`. No remote checkbox, label, or comment changed. A writable Git runner
must commit the test/evidence changes and complete the full source gates;
explicit live finding reassessment remains a separate pending acceptance check.
PR #4538 was verified open with `draft=false`.

## Current acceptance check — 2026-11-08

The historical notes below describe earlier attempts, not current deployment.
GitHub reports PRs [#4447](https://github.com/stranske/Workflows/pull/4447) and
[#4451](https://github.com/stranske/Workflows/pull/4451) closed with `merged=false`.
Their closure-bound helper implementation is not on `origin/main`. Instead,
commit `7ab99d09429a3b35aa55f7744f8c75b467f42536` (PR #4463) deliberately routes
all closed issues through verification, maps confirmed `verify` to forced `done`,
and revalidates PR/head evidence in the completion reporter. The previous helper
tests on this branch are retained; resurrecting their superseded completion
shortcut would conflict with the current production contract.

Inspected the source/template transition helpers, their tests, invoking workflows,
and `docs/AGENTS_POLICY.md`. The workflow redispatch condition already admits
successful `verify` with `verify_handoff=found`. The eligibility predicate rejects
`verify:pr-handoff` label events, but accepts `workflow_dispatch`, which supplies
the actual continuation. Label-event admission is therefore not required.

Pre-edit acceptance command:

```sh
timeout 60s node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
```

Expected observations: retained labels after reopening and a different PR's
closure select `verify`; a confirmed PR/head verifier handoff schedules forced
`done`; the guarded reporter posts `Auto-Pilot Complete` and removes
`agents:auto-pilot`. Failed dispatch must retain ownership without completion.
Stop rule: one baseline attempt and one post-edit attempt, each capped at 60
seconds; investigate a named failure before one corrective rerun. Full source
gates are separately bounded at 180 seconds each; timeout is incomplete, not PASS.

Baseline result: **97 passed, 0 failed** before implementation/test edits.

Canonical acceptance command after adding lifecycle coverage:

```sh
timeout 60s node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js .github/scripts/__tests__/auto-pilot-handoff-lifecycle.test.js
```

Result: **101 passed, 0 failed**, including the final run after restoring temporary
mutations. The script gate now includes the executable workflow suite through
`auto-pilot-handoff-lifecycle.test.js`. Its source and consumer cases each load
their own transition module, rather than both testing the root module.

The new lifecycle tests start with legacy `verify:evaluate`, execute the actual
verify script and redispatch script, evaluate the workflow's redispatch condition,
then execute the done reporter in a separate-run context without inherited
verify outputs. They assert one completion report and removal of ownership from
the correct issue. The reopening case retains both old labels and the old verifier
run, then requires a dispatch for the different PR and its different head.

Named deliberate-break checks (each run separately against source and template):

| Temporary implementation mutation | Named regression that failed (exit 1) |
| --- | --- |
| Trust `verifyHandoffBound` to select `closed-verified` | `issue 4365: reopening then closing with a different PR verifies the new PR` |
| Map `verify` redispatch to `auto` instead of `done` | `issue 4365: legacy verify:evaluate automatically completes and releases ownership` |

All four checks produced the named assertion failure. Both implementation files
were restored after every experiment; `git diff --exit-code --` on those files
passed. The first mutation-driver attempt could not spawn a nested Node process
(`EPERM`), so the successful checks invoked Node directly from the shell with
an EXIT trap restoring the original file. No mutation remains.

Additional verification:

- [x] `python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -m "not slow"`:
  **66 passed**, Python 3.14.10, normal plugin loading and warning policy.
- [x] `git diff --check` passes.
- [ ] `timeout 180s node --test .github/scripts/__tests__/*.test.js`: exit **124**;
  runner summary **115 passed, 6 failed, 20 cancelled**. The new lifecycle file
  passed. Failures include `agents-verifier-context.test.js`,
  `generated-delivery-seal-action.test.js`, `maint68-scoped-receipt.test.js`, and
  vendored dependency/verifier tests outside this change. A diagnostic rerun of
  the first two with isolation disabled reported **199 passed, 18 failed**,
  including child-process `EPERM` and a missing `delivery_not_sealed:staging`
  refusal message. No unrelated tests were changed or disabled.
- [ ] `timeout 180s python3 -m pytest -q tests/ -m "not slow"`: exit **124**;
  progress reached approximately 2%, without a final summary. This is not a
  passing full Python gate. Unlike historical attempts, plugin startup succeeded.

### Current live inspection — 2026-11-08

[Maint 68 run 42433992005](https://github.com/stranske/Workflows/actions/runs/42433992005)
completed successfully using source `c2ac6f38d6f2ce73f000158fa6f729bfece82092`.
Consumer PR #2454 records generated head
`b36b8ebf242bde649f6e31edc2cc915ad49d7421`, generation `4017589cec3c`.

The next observed [Maint 71 run 42434199041](https://github.com/stranske/Workflows/actions/runs/42434199041)
processed that exact head. Its report bound the head/source/plan, recorded
`review_state=clear`, `findings=[]`, `blocked=false`, and
`status=delivery_sealed_checks_pending`, requesting Gate rerun `42434160471`.
Its review mode was `integration-only`; this does not prove reviewer reassessment
of the two historical findings. The later
[Maint 71 run 42436928175](https://github.com/stranske/Workflows/actions/runs/42436928175)
still bound the same head and reported `campaign_prepared` with zero active review
threads. Neither report resolved the original threads.

GitHub currently marks discussions `4434491631` and `4434491675` **outdated, not
resolved**. Issue #4365's last sync-core bump names head `d6f4831035dd`, round
`20261106T115526Z`; its latest comments are closer/opener lifecycle notices.
The lack of a later bump, and integration-only empty findings, do not establish
that sync-core re-evaluated these findings successfully. Live acceptance remains
unchecked pending that explicit result on the generated head. No generated
consumer branch, workflow, or review thread was modified.

### Verified task progress

- [x] Inspect current source/tests/policy, prior PR merge state, and current main.
- [x] Record and run a bounded pre-edit acceptance command.
- [x] Add source/template reopening/different-PR regression coverage.
- [x] Add legacy handoff/automatic continuation/report/cleanup regression coverage.
- [x] Demonstrate named regression failures and passing results after restoration.
- [ ] Full Node and Python source gates pass.
- [ ] Explicit sync-core/reviewer live acceptance for the generated head.

Commit attempt: `git add` for the four changed test/documentation files failed
with `.git/index.lock: Read-only file system`; no commit was created. PR #4538
was read back as open with `draft=false`. Updating its verified checkboxes,
adding `needs-human`, and posting the concrete blocker comment were each rejected
with `MCP tool call requires approval, but approval policy is never`. No remote
checkbox, label, or comment change is claimed. The meaningful JavaScript test
changes remain in the working tree for a runner with Git write access.

Verified locally on 2026-11-04 for PR #4447. Reviewed prior commits
`e4c3bf7c`, `3e91bbc9`, `8e055ec0`, and `7d26be7c` before continuing.

## Verified helper behavior

- [x] The source and consumer transition helpers require matching source PR and
  closure identities before selecting `done`.
- [x] Reopening and closing again requires fresh handoff proof, including when
  the same PR closes the issue again.
- [x] Matching malformed identities on both records remain on `verify`.
- [x] Temporarily reintroducing label-only trust fails regression assertions;
  restoring both modules passes all transition tests.

The new tests cover matching invalid closure IDs and source PR numbers on both
records. Earlier malformed-input tests changed only one record, so equality
alone could satisfy those rejection assertions without validating either ID.

Command:

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js
```

Result: **43 passed, 0 failed**. Disabling process isolation exposes individual
test results in this environment; the default reporter displays a file result.

Three temporary mutations were checked separately in each module:

| Temporary regression | Observed result |
| --- | --- |
| Replace current-handoff validation with the handoff-label boolean | Exit 1, regression assertion fails |
| Remove closure-ID equality while retaining PR equality | Exit 1, regression assertion fails |
| Remove positive-ID validation while retaining identity equality | Exit 1, new matching-invalid-identity assertion fails |

All six mutations failed as expected. Both module files were restored in a
`finally` block. `git diff --exit-code` confirmed neither implementation file
retained a mutation, and the complete transition test file passed afterward.

A further mutation retained primitive-type validation while removing only the
positive-ID format check. On each module, the existing malformed-input test
passed while the new matching-invalid-identity test failed. Both modules were
restored, and all 43 tests passed again.

## Gates still incomplete

- [ ] `node --test .github/scripts/__tests__/*.test.js`
- [ ] `python3 -m pytest -q tests/ -m "not slow"`

The full Node run reported failures in `agents-verifier-context.test.js` and
`generated-delivery-seal-action.test.js` before it was interrupted while making
no further visible progress. Running those two files with process isolation
disabled yielded 199 passing and 18 failing tests, including child-process
`EPERM` errors. Those surfaces were not changed by this round.

The Python gate failed during `langsmith_plugin` startup: Python 3.14 emits an
`asyncio.iscoroutinefunction` deprecation warning, which the repository's warning
policy treats as an error. These results do not establish passing source gates.

The existing handoff integration tests passed separately with only that
third-party plugin disabled:

```sh
python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -m "not slow" -p no:langsmith_plugin
```

Result: **8 passed**. These tests exercise existing handoff labeling and lookup;
they do not verify automatic continuation or completion reporting.

## Maintainer follow-up: protected workflows

- [ ] Collect the current closure event and source PR; persist successful handoff
  identity and pass `closure` and `verifyHandoff` to `determineNextStep`.
- [ ] Accept eligible `verify:pr-handoff` label events in the gate predicate.
- [ ] Admit successful verification handoffs in the redispatch allowlist, or
  complete the done disposition in the same run.
- [ ] Validate current handoff identity in the done report before removing
  `agents:auto-pilot` and publishing completion.
- [ ] Test event eligibility, scheduled continuation, completion reporting, and
  label cleanup through the workflow.

These integration points are in `.github/workflows/agents-auto-pilot.yml` and
the consumer workflow template. The production caller currently passes only
the label-derived `verifyHandoffBound` boolean, without the identity objects
required by the helper. The event gate and redispatch allowlist also reside in
YAML. Helper tests therefore cannot establish automatic production completion.
No protected workflow was edited.

After merge, a maintainer should use Maint 68 to regenerate the selected consumer
payload, then verify Maint 71 and the review outcome for
`stranske/Portable-Alpha-Extension-Model#2454`. These live checks remain pending.

PR-body reconciliation, adding `needs-human`, and posting the workflow blocker
were attempted through the GitHub connector. All three writes were rejected
because the tool approval policy is `never`; this document preserves the
verified status and required follow-up locally. No remote checkbox, label, or
comment update is claimed.

The required commit is also pending: staging the two changed files failed with
`Unable to create .../.git/index.lock: Read-only file system`. The working-tree
test and evidence changes remain available for a runner with Git write access.

## Follow-up: execute the workflow callers

Added two regressions to `auto-pilot-transitions.test.js` that extract and execute
the actual automatic next-step Node caller from the root and consumer workflows.
Each runs a closed issue with retained handoff labels, reopens it, and closes it
with a different linked PR. The caller must select `verify` for the new closure,
and a legacy `verify:evaluate` issue without a bound handoff also remains on
`verify`. These checks exercise the production input mapping rather than supplying
identity objects directly to the helper. They do not establish successful
handoff continuation or completion reporting.

Verification:

- [x] `node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js`
  reports **45 passed, 0 failed**.
- [x] Replacing the identity guard with label-only trust in each helper separately
  makes its workflow-caller regression fail with `next_step=done`. Both helpers
  were restored in `finally` blocks; the tests pass again and neither helper
  retains a diff.
- [x] The existing workflow JavaScript tests pass alongside the transition suite.
- [x] The eight existing Python handoff tests pass with only the startup-failing
  LangSmith plugin disabled, using the targeted command above.
- [ ] Full source gates remain incomplete. The full Node run again reported
  failures in `agents-verifier-context.test.js` and
  `generated-delivery-seal-action.test.js`, then stopped producing output and was
  interrupted. The two failing files were rerun separately: **199 passed,
  18 failed**, including `spawnSync python3 EPERM` and a missing expected
  delivery-seal refusal message.
  The full Python run again exited during LangSmith plugin startup on the
  Python 3.14 deprecation warning, before collecting tests.

No protected workflow changed. The `needs-human` label and blocker comment were
again rejected by the connector's approval policy (`never`). PR #4447 was read
back as open with `draft=false`. Staging the test change again failed because
`.git/index.lock` cannot be created on the read-only Git metadata filesystem;
the meaningful test change remains uncommitted for the outer runner to collect.

## Follow-up: execute completion reporting

Reviewed commits `e4c3bf7c`, `8e055ec0`, `7d26be7c`, `1cb349b9`, and
`935d48cb`. Added tests that execute the actual `Report - Done` script from
both source and consumer workflows against a local GitHub API stub:

- Missing, absent, and incomplete handoffs retain `agents:auto-pilot`, report
  the retry reason, and refuse completion.
- A successful handoff in the current run removes `agents:auto-pilot` from the
  correct issue and posts the completion report.

These tests verify the reporter when invoked. They do not establish that a
successful handoff automatically reaches it or that its label-only input is
bound to the current closure. Those protected workflow tasks remain incomplete.

Verification:

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
```

Result: **49 passed, 0 failed**. The targeted Python command above also reports
**8 passed** with the startup-failing LangSmith plugin disabled.

Three temporary mutations of the extracted reporter were tested locally:
removing the missing-handoff guard, cleaning up a different label, and replacing
the completion heading. Each failed both new tests (exit 1). The temporary test
edits were restored in `finally`; the full focused suite passes afterward.
No workflow file was modified, even during mutation verification.

The full Node gate again reported failures in `agents-verifier-context.test.js`
and `generated-delivery-seal-action.test.js`, then stopped producing progress
and was interrupted. The full Python gate with `-m "not slow"` exited 3 during
LangSmith plugin startup on the same Python 3.14 deprecation warning. Neither
full source gate is complete.

PR checklist reconciliation was attempted before the new tests. The intended
reconciliation retains verified helper-identity and reopening tests while
unchecking unsupported continuation, event-gate, and end-to-end completion
claims. GitHub rejected the body update, `needs-human` label, and blocker
comment because the connector approval policy is `never`. No remote status
change is claimed. The workflow identity plumbing, event admission, successful
handoff continuation, and post-merge Maint 68/71 checks still require a maintainer.

Staging this round's test and evidence changes failed with `.git/index.lock:
Read-only file system`; no commit was created. PR #4447 was read back as open
with `draft=false`. `git diff --check` passes.

## Follow-up: serialized handoff status

Reviewed the five latest keepalive commits through `3ef2b6ab`. Added source and
consumer-helper regressions for a workflow boundary not previously covered:
matching closure/PR identities must still select `verify` when
`verifyHandoffBound` is the environment string `"false"`. False, missing and
empty values are rejected; boolean and serialized true values permit `done`.

- [x] Focused Node suites: **51 passed, 0 failed** using the command above.
- [x] Replacing handoff-flag normalization with JavaScript truthiness fails the
  new regression separately in each helper. Both files were restored in
  `finally`, then all 51 tests passed again. No implementation mutation remains.
- [x] Targeted Python handoff tests: **8 passed** using the documented command
  with only the startup-failing LangSmith plugin disabled.
- [ ] Full gates: Node again reported the same two failing files and was
  interrupted after progress stopped. Their diagnostic rerun produced
  **199 passed, 18 failed**, including `spawnSync git/python3 EPERM` and the
  missing delivery-seal refusal message. Python exited 3 during LangSmith plugin
  startup on the Python 3.14 deprecation warning, before collection.
- [ ] Remote reconciliation: body update, `needs-human` label and blocker comment
  were rejected because connector approval policy is `never`. Workflow-dependent
  task checkboxes must remain incomplete; helper-only verification is not
  production continuation. No remote update is claimed.
- [ ] Commit: `git add` failed because `.git/index.lock` is on a read-only
  filesystem. The test changes remain in the working tree for the outer runner.

The protected workflow integration and post-merge Maint 68/71 checks listed
above still require a maintainer. No protected file was edited.
