# Retained input-repair regression evidence

The `4231-original` and `4235-original` directories contain original request,
diff, event manifest, comparison, execution-receipt, and authenticated-readback bytes.
These are the retained raw outputs and execution evidence for both comments:

- `comparison.json`: The comparison result payload
- `comparison-execution.json`: The execution receipt for the comparison
- `authenticated-readback.json`: Authenticated readback of the original Actions publication
- `verification-event-manifest.json`: The verification event metadata
- `request-body.txt`: The original request body
- `verifier-pr-diff.patch`: The PR diff used for verification

The tests reproduce the original event identities without substituting requests or material.
The `authenticated-readback.json` retains the native Actions publication and original
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

## Expiry classifier evidence

Historical `2026-11-06-expiry-receipts.json`,
`2026-11-10-retained-payload.json` and `2026-11-10-expiry-receipts.json` are
preserved unchanged. The latter two reproduce an **offline** explicit
expired-artifact classification. Their provider-call and acceptance fields are
retained assertions, not freshly collected execution evidence. They must not be
used to claim current collector rejection, authenticated archive readback or
native admission.

### Authenticated continuation, checked 2026-11-10

`2026-11-10-authenticated-continuation/` retains a new read-only execution:

- `4231-collector.json` and `4235-collector.json`: complete actual JSON returned
  by `fetchVerifierEvidence` from the checkout's
  `.github/scripts/agents_verifier_context.js`.
- `execution.json`: UTC start/finish, source HEAD, collector and harness digests,
  Node version, explicit selectors, output digests, and every HTTP GET URL/status.
- `payload.json`: selected artifact identities, unchanged native diagnostics,
  authenticated required-comment status/digest, observed marker publication,
  and historical event identity. Execution evidence remains explicitly unknown.
- `receipt.json`: classifier output from that payload.

The executable `collect-retained-evidence.cjs` uses Node fetch with an
in-memory token obtained from `gh auth token`; it retains no token. Its API
adapter allows only GET requests in `stranske/Workflows` and contains no provider
adapter. Both calls explicitly select the proof comment, `comparison.json` and
`comparison-execution.json` in the retained artifact. Optional run and artifact
discovery are bounded to one record; native limit and unselected diagnostics are
retained without upgrading completeness.

```bash
# Use a new, absent output directory for each authenticated collection.
node tests/fixtures/verification_input_repair/collect-retained-evidence.cjs \
  tests/fixtures/verification_input_repair/2026-11-10-authenticated-continuation

/opt/anaconda3/bin/python3 tools/verifier_event_recovery.py \
  --classify-retained-artifact tests/fixtures/verification_input_repair/2026-11-10-authenticated-continuation/payload.json \
  --receipt tests/fixtures/verification_input_repair/2026-11-10-authenticated-continuation/receipt.json
```

**Fresh outcome: `incomplete evidence`; 0/2 authenticated retained readbacks or
native admissions.** Both required proof comments were included. Exact selected
artifact metadata lookups returned HTTP 404 (`selected artifact ID: Not Found`),
with `selected_metadata_lookup_failed` inventory entries. Each collector also
reported an unrelated unselected metrics artifact. The classifier consumes the
native `diagnostics.failures` and `diagnostics.archive_inventory`, binding each
failure to the exact selected artifact within that same record. Ambiguous or
unbound failures remain unknown.

The collector is an evidence reader. It does not establish execution-wide
provider-call counts or original-event acceptance. The new payload therefore
leaves both `provider_calls` and `original_event_accepting` null; the receipt
preserves both missing-evidence reasons. The probe itself constructed no provider
adapter and made only the recorded GET requests. No archive bytes were downloaded,
no new evaluation was requested, and no admission was attempted. The historical
2026-11-06 owner decision remains no fresh provider evaluation.

Blocking/drainable pair: selected retained archives and execution evidence are
unavailable / offline classification and focused regression checks remain usable.
Native admission requires the supported collector to authenticate the exact
retained result and execution receipt. Local historical result bytes and published
markers cannot replace that prerequisite. HTTP 404 establishes unavailability
under these credentials; it does not independently prove a retention-policy expiry.

Acceptance stop rule for this continuation: two failures at the same acceptance
step or 60 minutes. The first Python invocation stopped during pytest plugin
startup; disabling unrelated plugin autoload allowed the focused suite to run.
The historical offline receipts remain reproducible and separate from this new
live evidence.
