# Representative Verify API proposal (not executable)

This prospective revision is separate from the inactive square-pair plumbing
screen. The square fixtures establish transport and serialization behavior only;
neither those results nor unrelated typed-classifier benchmarks establish or
disqualify general PR Verify ability. No provider invocation is authorized here.

## Evidence and fixed matrix

The qualification owner supplies two real, fixed PR revision packets containing
the actual production prompt, original issue Tasks/acceptance criteria, exact PR
revision/diff and relevant source. Substantive judgments must be independently
frozen before provider output is observed. Those packets and judgments are still
pending; this document is not an executable replacement for them.

Use the existing two-provider compare path: first slot OpenAI `gpt-5.6-terra`,
second slot Anthropic `claude-opus-5-5`. Explicit CLI model overrides are positional
across credential-supported slots, so admission must assert both exact
provider/model identities before generation; a missing provider cannot shift a
model into the other slot. Preserve the existing cross-family comparison guard,
with no fallback or model-label substitution.

## Proposed production-compatible bounds

The proposed two-case package permits at most four generations, eight native
counts, six Anthropic metadata requests and eighteen physical HTTP sends, with
zero redirects, retries, repair or fallback. This is a proposed change from the
square screen's experimental bounds, not permission to enlarge that screen.
Each native SDK request uses the production 60-second timeout bounded by the
remaining package deadline. The package has a 600-second hard process-group wall
and an eleven-minute job limit. SDK timeouts are transport phase/inactivity
bounds, not a claim that a provider stops computing at that instant.

The production Anthropic Claude 5 builder explicitly reserves 128000 output
tokens, including thinking. The generic OpenAI factory leaves its output limit
unset; the actual semantic Verify capacity preparation switches the reviewed
Terra route to Responses and sets its missing output reserve from exact registry
facts, currently 128000. Preserve and check those actual native request policies;
do not infer one provider's policy from the other. Local SDK request-payload
observations are source behavior evidence, not provider capacity or entitlement.

The [Opus overview](https://platform.claude.com/docs/en/models/opus-5-5/overview)
documents the exact Claude API ID, one-million-token context and 128000 maximum
output. The dated registry entry does not invent an independent input limit:
fresh exact-model metadata supplies that input bound, and actual native token
counts plus the full output reserve must fit the documented context before any
generation. Missing/mismatched metadata, invalid counts or overflow hold.

The [migration guide](https://platform.claude.com/docs/en/models/opus-5-5/migration-guide)
requires thinking-aware response extraction and omission of sampling controls,
forced tools and assistant prefill. With no effort setting the documented Opus
default is **medium**, not High. The unchanged production builder sends no effort
claim. Inert controls use real SDK `Message`, `ThinkingBlock` and `TextBlock`
objects through the native response conversion and existing strict parser; only
the text block supplies the verdict JSON. The raw thinking block is not a verdict.

## Exact remaining source work

The existing square runner rejects other packets, model overrides and larger
limits. It remains disabled. Once the owner freezes the two real packets, a
separately reviewed finite source variant must bind their hashes, exact model
mapping and the above per-provider native policies; update the exact Opus metadata
HTTP path; use the eleven-minute/600-second job and process limits; and retain
private-first credential-safe output publication. No caller paths, arbitrary
endpoints, secret exports, new credentials or general execution facility are
needed. Do not enable the source policy or dispatch before assembled review.

Report substantive correctness, usable text/serialization, operational completion
and comparison outcome separately. Preserve raw observations and exact failure
reasons. A correct answer is not rejected for bespoke citation/tag formatting,
and an incomplete run is not reported as a completed qualification.
