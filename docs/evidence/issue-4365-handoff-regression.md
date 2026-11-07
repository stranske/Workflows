# Issue #4365: closure-bound verify handoff helpers (reduced PR #4451)

PR #4451 was reduced on 2026-11-06 to the finished helper work. Issue #4365
stays open for the deferred workflow integration.

## Retained scope

In `.github/scripts/auto_pilot_transitions.js` and its identical consumer
template copy:

- `hasCurrentVerifyHandoff(event)` returns true only when `verifyHandoffBound`
  is boolean true or a serialized true string, the closure ID and source PR on
  both `event.closure` and `event.verifyHandoff` are positive integers (number
  or digit string), the closure IDs match and the source PRs match.
- `resolveCurrentState` returns `closed-verified` for a closed issue only when
  that check passes; otherwise it stays `closed-needs-verify`.
- `selectMergedClosingPr(pulls, issueNumber)` returns the first merged PR whose
  body or title carries `meta:issue:<n>` or a closing keyword `#<n>`, with the
  issue number digit-bounded so `#120` never matches issue 12.

## Production effect

None yet. On this base the auto-pilot workflows do not pass `closure` or
`verifyHandoff` to the helpers and do not call `selectMergedClosingPr`, so
closed issues keep routing to `verify` exactly as before. The helpers become
live only when the deferred workflow wiring lands.

## Deferred to the follow-up on #4365

- Structural-context (fenced/quoted) parsing for keepalive and handoff markers.
- Validation of the configured handoff writer identity.
- Workflow wiring in both `agents-auto-pilot.yml` copies: closure/source-PR
  collection, handoff persistence, label-event admission, redispatch and
  identity-validated completion.
- Bounded cycle accounting replacing lifetime step-comment counting.
- `tests/workflows/auto_pilot_verify_handoff.test.js` per-surface helper fix.
- Consumer sync (Maint 68/71) for Portable-Alpha-Extension-Model#2454.

## Validation

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js
```

Result on 2026-11-06: 50 passed, 0 failed. Covered: reopened issues, same-PR
reclosure, different source PRs, matching malformed identities, serialized
false flags, and merged-PR selection on both surfaces.

## Acceptance verification (2026-11-07)

- [x] `hasCurrentVerifyHandoff` requires a true handoff flag, valid positive
  closure/source-PR identities on both records, and matching identities;
  `resolveCurrentState` gates `closed-verified` on that proof.
- [x] `selectMergedClosingPr` selects the first merged matching PR in input
  order, from either body or title, with digit-bounded issue references.
- [x] Focused regressions cover reopening, same-PR reclosure, different source
  PRs, matching malformed identities, serialized false flags, and merged-PR
  selection on both surfaces. Two new fixture cases cover same-PR reclosure
  and a serialized false flag with otherwise matching proof.

The existing helper implementations already satisfied these criteria. Added
direct helper/state assertions for independently invalid fields on both records,
body/title closing-keyword cases, first-match ordering, and invalid PR batches.
All transition fixtures now execute against both source and consumer helpers.
The two helper files remain byte-identical.

```sh
node --test --test-isolation=none .github/scripts/__tests__/auto-pilot-transitions.test.js
node --test --test-isolation=none tests/workflows/auto_pilot_verify_handoff.test.js
python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py tests/workflows/test_sync_manifest_delivery.py tests/scripts/test_template_drift_allowlist.py -m "not slow"
python3 scripts/check_template_drift.py
```

Results: 80 helper tests passed; 46 workflow handoff tests passed; 91 Python
tests passed; drift validation exited 0 with no unallowlisted drift.

A broader combined JavaScript run including
`.github/scripts/__tests__/verifier-correction-wiring.test.js` passed 145 tests
and failed one existing runner-assembly test at line 167 because
`spawnSync python3` returned `EPERM` in this execution environment. No test or
security control was disabled to bypass that failure. Workflow integration and
consumer delivery remain deferred as described above.

## Additional regression validation (2026-11-07)

Reviewed commits `92879ba6` and `71a65646` and re-ran the existing 80 helper
tests before reconciling the three retained tasks. All three are implemented;
the source and consumer helper files remain byte-identical.

Added regressions on both surfaces for distinct decimal-string identities above
JavaScript's safe integer limit, and for prefix issue references in either the
PR body or title preceding a valid closing PR. Adjacent large IDs must not
compare equal after numeric rounding; `#120` must not shadow issue 12.

Validation using the commands above: 84 helper tests and 46 workflow handoff
tests passed (130 combined); all 91 targeted Python tests passed; template
drift validation exited 0 with no unallowlisted drift. The broader JavaScript
run passed 149 tests and retained the same single `spawnSync python3 EPERM`
runner-assembly failure described above.

The PR-body reconciliation could not be published: the GitHub update tool
requires approval, while this run's approval policy is `never`. The prepared
body is saved at `/tmp/pr-4451-body.md` with all three verified tasks checked.
Committing was also blocked: Git could not create `.git/index.lock` because
the repository metadata directory is read-only. The changes remain uncommitted.

## Handoff flag type regression (2026-11-07)

The first retained task had one remaining type-validation gap: arrays such as
`["true"]` and objects stringifying to `"true"` could authorize a handoff with
matching identities. Added a direct regression on both surfaces and confirmed
both tests failed before changing the helpers. Both helpers now accept only
boolean true or serialized true strings for the handoff flag, preserving the
existing case/whitespace normalization for workflow environment strings.

Validation:

```sh
node --test --test-isolation=none --test-reporter=dot .github/scripts/__tests__/auto-pilot-transitions.test.js tests/workflows/auto_pilot_verify_handoff.test.js
python3 -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py tests/workflows/test_sync_manifest_delivery.py tests/scripts/test_template_drift_allowlist.py -m "not slow"
python3 scripts/check_template_drift.py
git diff --check
cmp .github/scripts/auto_pilot_transitions.js templates/consumer-repo/.github/scripts/auto_pilot_transitions.js
```

Results: 86 helper tests and 46 workflow handoff tests passed (132 combined);
all 91 targeted Python tests passed. Drift validation found zero unallowlisted
differences; the helper copies are byte-identical. The existing two fixture
cases and the merged-PR selector regressions still pass.

Commit remains blocked: `git add` cannot create `.git/index.lock` because the
repository metadata directory is read-only. Consumer delivery requires the
source commit to be published first, so no sync was dispatched for this local
change. PR #4451 was confirmed open and ready for review (`draft=false`).
Posting the blocker comment also failed: the GitHub tool requires approval,
while this run's approval policy is `never`.
