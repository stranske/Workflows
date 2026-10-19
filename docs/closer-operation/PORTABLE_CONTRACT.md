# Portable closer Core (`closer-operation/v1`)

Workflows owns **Workflows Closer Core**: the portable record schema, target/action CAS
fence, transition guards, and expected-check producer. **Orchestrator Closer Runtime**
remains separately owned and distributed by Orchestrator: queue selection,
capacity, installation, local runtime acceptance, and runtime execution. Core
imports no Orchestrator source and does not install, schedule, merge, or run a
production verifier. Neither repository is renamed.

Distribute a pinned Workflows source revision containing `scripts/closer_runtime.py`,
`scripts/closer_operation_github.py`, `scripts/check_checks_reported.py`,
`scripts/api_client.py`, `scripts/reusable_ci_scope.py`, the producer's supported
workflow definitions, and `fixtures/closer-operation/v1/`. Dependencies are Python
3.12+, jsonschema, PyYAML, requests, and authenticated `gh` for topology reads.
The new Core contract/store files are not fleet-synced: there is no entry for
them in the consumer sync manifest. Existing shared dependencies retain their
current distribution entries.
A source-only checkout is not evidence of deployment or a live closer canary.

## Authority and record boundaries

`canonical_target_fence_key(spec)` binds repository/PR/action across heads.
`canonical_operation_key(spec)` also binds head/base, original criteria, review,
guard versions, required capabilities, and blocking labels. Stripping a runtime
acceptance label therefore changes the spec and cannot reuse its authority.
Every read and write validates the actual shipped JSON Schema, canonical keys,
repository, and store-key boundary. Updates advance revision exactly once;
owner/spec changes advance epoch exactly once. Earlier scaffold records with
keys that omit policy fields fail validation; Core never silently rewrites or
migrates retained denials or unresolved outcomes.

`LocalOperationStore` uses flock, fsync, atomic replacement, and directory fsync
for **local progress only**. `GitHubContentsOperationStore` implements the same
`claim(spec, executor, lease_deadline=...)` protocol, using conditional Contents
writes as the global target/action fence. `expected_revision=None` is create-only;
updates supply the observed remote blob SHA. A lost CAS never grants ownership.

The shared store reuses `keepalive-authority-state`, under the separate
`.github/closer-operation-portable/v1/` namespace. `bootstrap()` explicitly
creates the branch at the default-branch head only when absent; it never resets
an existing branch or changes keepalive v2 records. `NativeGitHubTransport`
performs single-attempt HTTPS requests with an independently supplied token.
Constructing it performs no network requests. Calling bootstrap/claim/write is
an explicit remote mutation and requires authorization in the consuming runtime.

All participating portable executors must use this shared namespace for global
ownership. Existing keepalive v2 records retain their original run-attempt
protocol; merely sharing a branch does not make the two protocols mutually
exclusive. Wiring any additional runtime into Core remains a separate rollout.

A contents 404 establishes absence only after repository and authority-branch
reads succeed. Permission denial raises `PolicyDenied(no_fallback=True)`;
service/read failures raise `RemoteUnavailable`; unproved write outcomes raise
`UnknownOutcome`. Unknown POST/PUT outcomes are read back before any resubmission;
exact desired-record readback resolves a lost PUT response. A diagnostic cache
is accessed explicitly through `cached_observation()` and is never consulted
by shared claims or writes. It cannot grant global ownership.

## Bounded verification

The only production verification adapter is `expected_check_topology`.
`verify_expected_checks` invokes Workflows'
`collect(Evidence(native_gh_pages), repo, pr, head, event, action)` directly.
`verify_unchanged_gate` is a compatibility alias for that real check;
`execute_local_verification` accepts only the same fixed adapter. The static
fixture adapter is rejected. Caller verdict, source, digest, and command-path
fields cannot choose a producer or supply its result.

Receipts retain the actual producer result, request evidence, producer/helper
source hashes, original criteria/review fingerprint, and result digest. Every
invocation collects fresh evidence; only an exact successful result is
coalesced with a prior successful receipt. FAIL and UNKNOWN never populate the
successful cache. Unsupported topology stays UNKNOWN. A topology PASS does not
authorize merge or replace review threads, the post-push floor, runtime
acceptance, or other receiving-runtime gates.

The standalone expected-check CLI supports `--transport native-gh`, with no
incumbent import. Its optional incumbent mode still accepts the trusted
`--presence-reporter` and retains the original source/provenance semantics.
Neither mode copies the historical frequency/ratchet algorithm.

## Ownership and reconciliation

`verify_request` records dispatch of a merge-bound `verify:compare` request, not
verification acceptance or an expected-check topology PASS. Its operation identity
and readback are distinct from `verify`; both share the original `verify` CAS
fence so upgrading Runtime cannot bypass an older unresolved operation or denial.
Request completion requires the native Runtime's exact-head, exact-merge PR/label
readback; Core's topology producer cannot reconcile a `verify_request`.

Transition functions require executor identity, spec, expected epoch, and
expected revision. `run_bounded_action` and its `run` CLI require the epoch and
revision too. Expiry blocks execution; it never evicts a writer or clears an
unknown outcome. No timed engineering permit is introduced.

Denied records cannot transfer. Denial/no-fallback survives a new head, spec,
executor, and channel; Core exposes no permission-reset authority. A fresh
independent authorization needs an authority integration outside caller receipts.
`native_runtime_ac_authorization` data cannot grant permission, even for an
executor named `orchestrator_local`. Portable runtime-AC merge intent remains
hardblocked.

Submitted/uncertain operations cannot retry mutation. They may hand off only
with `reconciliation_only=True`; that scope persists and cannot grant execution.
Reconciliation requires typed `ReconciliationEvidence`, bound to operation,
target/action, head, observation result, source, and digest. An absent desired
result stays uncertain. Success requires an observed desired result. The CLI
collects its own fixed read-only evidence (topology for verify, exact-head PR
merged state for merge), ignoring caller verdicts and observation booleans.
The Python evidence API is for trusted adapters; a caller with arbitrary Python
or filesystem execution is not a security-isolated principal.

## Local verification

```bash
python3 -m pytest tests/scripts/test_closer_runtime.py \
  tests/scripts/test_closer_portable_boundaries.py \
  tests/test_check_checks_reported.py -q
```

Tests use fake native HTTP and complete REST fixtures, including 409/422, 403,
timeout-after-write, two contenders, explicit lease expiry, schema/key corruption,
and actual killed subprocesses after submission and before atomic replacement.
No live network, shared claim, queue, installation, or production verifier is
needed for these tests. Live provider permissions, branch policy, publication,
and end-to-end runtime integration are separate, unverified boundaries.

## Expired leases, guarded writes and recovery (independent-review follow-up)

- **Guarded store writes.** `write_cas` is public but requires a `WriteAuthority`
  (purpose, writer identity, expected epoch). The validator, shared by the local and
  GitHub Contents stores, enforces: owner and live lease for `owner_update`/`transfer`;
  immutable identity fields, append-only receipts and write-once `mutation_intent`; no
  lease extension outside an acknowledged replacement; `submitted` only from a recorded
  intent; a new spec only as a clean `claimed` record over a drained (`succeeded` /
  `unavailable`) one; the runtime-AC barrier on any write that records or submits intent.
  Supported contract: every public API path is guarded. A process that holds the store
  credentials can still forge a record by bypassing this module; no security boundary
  against a malicious credential holder is claimed.
- **Read-only recovery after expiry.** Expiry never proves a write did not start and never
  authorizes retry. `reconcile_unknown` (and the `reconcile_submitted` bounded action) work
  on `intent_recorded` (after expiry), `submitted` and `uncertain` records past the
  deadline, from the owner or an independently scheduled observer. A non-owner observer
  fences the old owner (epoch + 1, reconcile-only), leaves the original deadline, intent
  and every receipt untouched, and appends one operation-bound receipt. Only a positive
  producer-read desired result yields `succeeded`; `not_observed`, `unknown` or an absent
  result stay `uncertain`. A non-owner cannot do this while the lease is live.
- **Replacement of read-only claimed work.** `replace_readonly_claim` replaces an expired
  owner of a `claimed`, no-intent, non-merge operation, only with an explicit
  acknowledgement; it bumps the epoch, sets a new deadline and keeps the old one in
  `lease.prior_deadlines`. Intent, submitted and uncertain records cannot be handed off for
  write; `intent_recorded` transfers are reconcile-only.
- **Write outcomes (GitHub Contents).** Only a denial that originates from the PUT is a
  known refusal (`PolicyDenied`, no fallback). Anything that fails after the PUT was
  sent, including a readback 401/403, is `UnknownOutcome` (carrying `no_fallback` when the
  readback was denied). A 403/429 carrying rate-limit headers or text is
  `RemoteUnavailable` (capacity), not a permission denial. PUT/POST are never retried.
  The native transport allows only the authority branch ref, the portable contents
  namespace and repo metadata reads.
- **Context binding.** `OperationSpec.verification_event/_event_action` are part of the
  operation key, the record (`verification_context`) and verification reconciliation
  receipts (`context`). An unbound spec uses the producer default (`pull_request` /
  `synchronize`); a payload naming any other context is refused, never substituted.
- **Runtime-AC labels.** Core coordinates only; it grants no merge permission and no
  caller flag or receipt is runtime-AC authority. Merge intent, submission and evidence
  recording union caller labels with fresh PR labels read by the fixed GET-only producer
  bound to the head; an unreadable label set fails closed. Every caller keeps its own
  native guard and independent authorization.
- **Known gaps.** The label read is at action time, not atomic with the merge. A different
  executor cannot claim a new spec over another executor's drained record (unchanged).
  Executor identity is a free-form string; two processes sharing one inherit ownership.


## Pinned distribution and successor history

`scripts/closer_core_package.py build` creates a fresh immutable package directory
with a public relative-path descriptor. It never replaces an existing destination.
Verification checks the closed file set, entrypoint, file digests and declared
interpreter dependencies. Host paths and credentials belong in a separate local
binding. The tested minimum is jsonschema 4.22.0; the descriptor pins PyYAML and
requests versions. Runtime launch cannot override the sealed package environment.

A changed specification may replace a legally drained operation. A different
executor must explicitly acknowledge replacement. The exact prior record and its
canonical digest remain in an append-only flat `prior_operations` history. The
history is bounded at 64 entries; reaching the bound holds rather than dropping
evidence. Denials and unfinished mutation intents cannot become drained through
an unavailable outcome. After intent, capacity/service failure retains uncertainty
until typed reconciliation establishes the result.

The package `verify` CLI requires `--expected-digest` from a trusted source outside
the package. Its internal descriptor cannot authenticate itself. The sealed runner
probes dependencies with the same interpreter, environment and working directory
used for execution. Native expected-check mode permits exactly the GitHub Actions
app and bot publisher-identity reads needed for a required `Gate / gate` context.
