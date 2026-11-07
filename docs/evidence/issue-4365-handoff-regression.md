# Issue #4365: closure-bound verify handoff helpers (reduced PR #4451)

PR #4451 was reduced on 2026-11-06 to the finished helper work. Issue #4365
stays open for the deferred workflow integration.

## Retained scope

In `.github/scripts/auto_pilot_transitions.js` and its identical consumer
template copy:

- `hasCurrentVerifyHandoff(event)` returns true only when `verifyHandoffBound`
  is true, the closure ID and source PR on both `event.closure` and
  `event.verifyHandoff` are positive integers (number or digit string), the
  closure IDs match and the source PRs match.
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
