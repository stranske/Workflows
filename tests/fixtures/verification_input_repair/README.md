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

`2026-11-06-expiry-receipts.json` records the historical classified retained-artifact outcome
for comments `6390994169` and `6392557346` using the real authenticated read-only collector
invocation from `fetchVerifierEvidence` in `.github/scripts/agents_verifier_context.js`.
The separate dated receipt `2026-11-10-expiry-receipts.json` records the operational rerun
produced from the executable retained payload `2026-11-10-retained-payload.json`.

The offline classifier outcome is `explicit expired-artifact rejection` for
comments `6390994169` and `6392557346`. The supported collector's explicit
expiry rejection remains unestablished. Published markers and local `comparison.json`
bytes are recorded and are not authenticated Actions readback or native
admission. Both original events stay nonaccepting. Observed provider calls are
integer zero. The 2026-11-06 owner decision is no fresh provider evaluation.

### Executable collector invocation

The real authenticated read-only collector is invoked via Node.js using the
`fetchVerifierEvidence` function from `.github/scripts/agents_verifier_context.js`:

```bash
node -e 'require("./.github/scripts/agents_verifier_context.js").fetchVerifierEvidence({
  github: <authenticated_octokit_client>,
  owner: "stranske",
  repo: "Workflows",
  pullNumber: <pr_number>,
  pullRequestBody: <pr_body>,
  associatedCommitShas: [<commit_shas>],
  evaluatedSha: <evaluated_sha>
})'
```

This performs authenticated Actions archive lookup and returns the retained evidence
for both comments 6390994169 and 6392557346, including HTTP 404 status, proof status,
and marker publication state. The collector outputs are then converted to observation
format and fed into the classifier.

### Executable classifier invocation

```bash
python3 tools/verifier_event_recovery.py \
  --classify-retained-artifact tests/fixtures/verification_input_repair/2026-11-10-retained-payload.json \
  --receipt tests/fixtures/verification_input_repair/2026-11-10-expiry-receipts.json
```

Where `tests/fixtures/verification_input_repair/2026-11-10-retained-payload.json` contains
the observation rows with `comment_id` and `marker_published` (with `marker_published` set to `true`),
using the retained subject, proof, HTTP 404 and local `4231-original/comparison.json` /
`4235-original/comparison.json` paths under this fixture tree.

### Observation keys

- `comment_id`: The GitHub issue comment ID (`6390994169` for #4231, `6392557346` for #4235)
- `marker_published`: Boolean indicating whether the verifier-input-repair marker was published (`true` for this receipt)
- `artifact_http_status`: HTTP status code from the Actions archive lookup (`404` = not found)
- `original_event_accepting`: Boolean acceptance status of the original event (`false`)
- `provider_calls`: Integer count of provider invocations (`0` for no provider calls observed)
- `published_archive_sha256`: SHA-256 digest of the published archive
- `subject`: Contains `event_id`, `material_sha256`, `head_sha`, `evaluated_sha`, `request_sha256`
- `proof_status`: Status of the proof comment (`included`)
- `proof_body_sha256`: SHA-256 digest of the proof comment body
- `local_archive_path`: Relative path to local comparison bytes

### Classifier output vs collector rejection

The classifier produces offline classification based on retained evidence. It distinguishes:
- **Explicit expired-artifact rejection**: HTTP 404 or explicit expiry marker with no provider calls
- **Authenticated retained readback**: Archive bytes match published digest with valid evidence
- **Identity mismatch**: Comment/artifact identity doesn't match known retained artifacts
- **Missing status**: Required status fields are absent
- **Incomplete evidence**: Missing or invalid `provider_calls` or `original_event_accepting`

Collector rejection (`fetchVerifierEvidence`) occurs when archive bytes are unavailable,
which is a prerequisite failure, not a classifier outcome. The classifier only runs
after the collector succeeds or with pre-authenticated local fixtures.

### Historical receipts and proof gaps

Historical receipts from the original runs are preserved in `4231-original/` and
`4235-original/`. The proof gaps (unavailable archives) are documented in the
`remaining_gaps` field of the expiry receipt. No new hash is substituted for fresh
observations; the original published archive digests are retained.

### Source revision and working-tree state

- Source revision: `8c678c19a4f9f60fa5be6a00f08794a9626c87bd`
- Working-tree state: Clean, with no uncommitted changes
- Both comment outcomes: Explicit expired-artifact rejection
- Explicit provider-call evidence: 0 (no provider calls observed)
- Cumulative stop-rule result: Not exhausted (1/2 attempts used)
