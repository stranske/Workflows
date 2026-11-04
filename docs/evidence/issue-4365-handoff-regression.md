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
