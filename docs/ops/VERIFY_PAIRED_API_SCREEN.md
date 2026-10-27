# Fixed public paired Verify API screen

MAINT-78 has a separate `verify-paired` mode for the independently reviewed
public `square-pass` / `square-nonpass` packet. The old `assess` job is excluded
only for that mode. The new job runs only from the repository default branch,
has `contents: read` permission, disables checkout credential persistence, and
maps only the existing `OPENAI_API_KEY` and `CLAUDE_API_STRANSKE` secret names.
It has no comment, issue, PR, token-minting, dispatch, or repository-write step.
Evidence is retained as a seven-day Actions artifact.

**Source preparation only:** `config/verify_paired/trial-policy.json` currently
has `execution_enabled: false` and `review_status: proposed_source_only`.
The command writes a held receipt before any client construction or provider
request. Core and the executor must review the exact code and caps before a
separate source change can enable it. This preparation does not authorize a
dispatch or API invocation.

## Frozen input and existing execution path

`tools.run_verify_paired` accepts no case path, model, endpoint, or repository
argument. It verifies the original proposal SHA-256
`3423da3d0c0f243f10d83f57e2243d5ce04b30511b5dbd589919b5ca4e3620b9`,
all retained original packet file hashes, and the independent review digest.
The preparer's original `build.py` digest is retained in the proposal; that
program is neither copied nor executed. The retained build receipt records its
original source revision and synthetic content-derived head identities. Those
identities are not attested Git commits or production PRs.

For each of the two fixed cases, the wrapper invokes the existing
`scripts/langchain/pr_verifier.py --compare --json` CLI. Compare returns before
the existing create-issue branch. Each case is copied to the runner's temporary
`verify-paired` directory; the source packet is never rewritten. An ephemeral
32-byte semantic-envelope key is deleted in cleanup and excluded from artifact
retention. That existing local envelope signature is not a remote attestation.

The optional semantic policy validates exact original capture identity, both
fixed provider/model slots, one complete package, and the reviewed full prompt
hash before client construction. It uses the existing native clients, capacity
contracts, full-matrix count preflight, immediate pre-generation recount,
semantic response parser, raw response provenance and acceptance ledger. It
adds no fallback, repair, retry, endpoint, provider, subscription credential,
selection promotion, or general qualification framework. Ordinary comparisons
without the optional policy keep their existing client options and behavior.

The candidate API IDs are `openai/gpt-5.6-terra` and
`anthropic/claude-sonnet-5-5`, both provisional for the Verify role. The current
source registry supplies exact-model capacity facts; Anthropic additionally
requires its existing native model-metadata lookup. Missing or malformed native
facts, missing keys, unavailable entitlement, count failure, malformed response,
and exhausted policy bounds remain held/incomplete. Neither key presence nor a
policy ceiling proves native account capacity or role qualification.

## Proposed restrictive trial caps

These are policy ceilings awaiting Core/executor review, not new native model
capacity facts:

| Boundary | Proposed maximum |
| --- | ---: |
| Generations, two cases combined | 4 |
| Native input-count requests | 8 |
| Anthropic native model-metadata reads | 6 |
| Generation output ceiling, including reasoning where applicable | 4,096 tokens |
| SDK request timeout | 30 seconds |
| Wrapper execution wall time, both CLI processes combined | 300 seconds |
| Workflow job wall time, including dependency setup | 6 minutes |
| Retries, repair calls, model/provider fallback | 0 |

Each case allows at most two generations, four counts, and three metadata
reads. Budgets count attempts before the native method is called. Both existing
SDK-owned HTTPX clients have redirects disabled in this optional policy, and
native SDK retries remain zero. Thus a complete fixed pair uses at most eighteen
native HTTP attempts, including metadata; redirects cannot silently add calls.
The SDK timeout is a request/IO timeout, not an independently enforced complete
call wall time. The parent subprocess timeout enforces the combined wall cap.
An uncertain or failed attempt is retained without relaunching that case.

Actual native-shaped SDK tests use HTTPX MockTransport only, including redirects,
503 responses, timeout and entitlement refusal. They establish source behavior,
not real provider execution. Additional existing compare tests cover ordinary
behavior. No live calls, dispatches, account checks or secret-value reads are
part of source preparation.

## Evidence and separate executor judgment

The artifact retains each original public case, raw structured comparison JSON,
human report, diagnostics, capture/reassembly manifests, and an invocation
receipt. The semantic envelope adds attempted count/generation/metadata totals
and the exact policy. Native capacity and role-qualification claims are always
false in the invocation and trial-policy records. The original oracle remains
outside the model prompt; the category-2 executor owns evaluation against it.
Two easy public screens cannot qualify the full Verify role or authorize ACT,
correction effects, source closure, deployment or model promotion.
