# Issue #4365: handoff regression verification

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
