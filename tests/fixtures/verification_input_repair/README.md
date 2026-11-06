# Retained input-repair regression evidence

The `4231-original` and `4235-original` directories contain original request,
diff, event manifest, comparison and execution-receipt bytes. The tests reproduce
the original event identities without substituting requests or material.
`authenticated-readback.json` retains the native Actions publication and original
history, plus the supported collector's complete required-comment readback.

The historical ZIPs were read from the source coordinator's
`run-20261025T1247-source-delivery4239` receipt directory. Before extraction,
their SHA-256 digests were checked against the freshly fetched native publication
comments. Result and receipt member hashes, original material, request body and
diff hashes were also checked. No result bytes, verdicts or original state
markers were changed.

| Target | Original run / artifact | Authenticated ZIP SHA-256 |
| --- | --- | --- |
| #4231 | 40143755394 / 12579928048 | `c432b89fca7af092f08bc6cddf032b62b2f15ac0c727e75b9fcb30b9695e9d58` |
| #4235 | 40155311407 / 12584318436 | `526dcef67f26160ece176b800e7a4d18a2e6d6883d7a2e4294b07570570486ab` |

## Operational acceptance, checked 2026-11-02 America/Chicago

Before editing, the recorded real-input acceptance command was
`node /private/tmp/workflows-4239/acceptance.cjs`. The outcome required both exact
retained events to pass complete supported collection and native admission after
source delivery, with lineage, deduplication and no provider before admission.
The stop rule was three acceptance attempts or 60 minutes. One live attempt ran.

`2026-11-02-live-receipts.json` records that attempt using the current main
collector (`buildVerifierContext` and `fetchRequiredConversationComments`) through
authenticated Octokit 20.0.2. The harness permitted only GitHub read operations
(including read-only GraphQL) and local git diff. It constructed no provider
adapter. Its scratch source and output remain under `/private/tmp/workflows-4239/`.

**Live outcome: 0/2 admissions.** Both proof comments were completely included;
the execution-history guard returned `ready`. PR #4242 source delivery was read
back as merged at `99829d194588de062d88cad093e53a838b0351b2`. Both original result
artifacts returned HTTP 404. The collector refused with
`Required verification artifact member is absent, ambiguous or incomplete`.
Native capacity admission was not reached. Live resulting-event lineage and
deduplication remain unresolved. Both original events remain incomplete and
nonaccepting; no provider ran.

Blocking/drainable pair: original result artifacts unavailable / the existing
supported collector must authenticate the exact retained result and receipt
before native admission can proceed. Local historical bytes establish regression
coverage only; they do not replace that live prerequisite. No alternate artifact
publication, rebuilt-event dispatch or provider retry was attempted. Historical
OpenAI `UNVERIFIABLE_INPUT` and Anthropic `PASS` remain separate from delivery
acceptance.

## Digest deliberate-break gate

The required command was run with the single artifact equality expression
`|| found[0].raw_sha256!==claim.raw_sha256` temporarily removed from
`authenticatePredecessor`'s `authenticateInputRepair` path. Only
`#4231 negative matrix: wrong artifact digest is rejected` and its #4235 counterpart
failed: 51 pass, 2 fail, exit 1. Source bytes were restored in a `finally` block
and verified against their recorded SHA-256:

`d2b0e789efba0e966f5c68789e0e5ec8533e615660a7afad26513df67ef1785b`

After restoration:

```text
$ node --test tests/scripts/test_verification_event.js tests/scripts/test_verification_input_repair.js
tests 53
pass 53
fail 0
skipped 0
exit 0
```

`2026-11-02-digest-gate.json` records the hashes and exit statuses. The PR body
contains full command output. Separate broader regression validation passed
122 tests, with one optional downloaded #4238 archive test skipped. Production
source remains byte-exact; this change adds fixtures, coverage and receipts.

## Expiry decision, checked 2026-11-06

The retained result artifacts `12579928048` (#4231) and `12584318436` (#4235)
still return HTTP 404. `2026-11-06-expiry-receipts.json` is the read-only
collector run plus `classify_retained_artifact_report`. The operational outcome
is `explicit expired-artifact rejection` for comments `6390994169` and
`6392557346`. Published markers and local `comparison.json` bytes are recorded
and are not authenticated archive readback or native admission. Both original
events stay nonaccepting. Provider calls are zero. The 2026-11-06 owner
decision is no fresh provider evaluation. `2026-11-06-digest-gate.json` records
the temporary removal of `|| found[0].raw_sha256!==claim.raw_sha256`, the two
named wrong-artifact-digest failures, and the byte-exact restore
(`d2b0e789efba0e966f5c68789e0e5ec8533e615660a7afad26513df67ef1785b`) followed
by 55 passing tests.
