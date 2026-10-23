# Verification events

Initial and repeat evaluations use `agents-verifier.yml` and the same reusable
collector, input admission, evaluator, CI hard gate and report publisher. A repair
merged in another PR is evaluated as that actual delivery PR. An old PR number
cannot be used to request evaluation of an arbitrary later commit.

`verification-event/v1` identifies the exact repository (lowercase), PR (string),
original head, evaluated merge, original-request digest and material digest.
`event_id` is SHA-256 of sorted, compact JSON containing `schema`, `repo`, `pr`,
`head_sha`, `evaluated_sha`, `request_sha256` and `material_sha256`. The independent
Python/JavaScript fixture is `tests/fixtures/verification_event/canonical.json`.

The request digest covers the full original PR and authentic linked issue bodies,
with their repository, kind and number, in `verification-request/v1`. The material
digest covers the retained full diff and explicitly selected necessary evidence
in `verification-material/v1`. Its `ci_hard_gate` inventory retains only the
existing configured gate's workflow identity, exact delivery head, run, attempt
and conclusion. Missing provenance stays explicitly absent or unavailable. The
collector never credits a later wrapper commit's CI or a different-head API
fallback as current delivery proof. Existing CI gate sufficiency rules remain
in force. Job summaries, links and unrelated workflows are excluded.
The digest excludes clocks, retrieval counters, optional
logs, archive packaging, evaluator outputs and the prior-verdict event identity.
Adding a predecessor alone therefore cannot create fresh material or a new event.

The optional workflow inputs are:

- `verification_event`: expected event JSON. The collector recomputes it from
  authoritative inputs and refuses a mismatch before model invocation.
- `verification_material`: at most 20 JSON selectors from the existing necessary
  evidence collection plan. A comment selector is `{"kind":"comment","url":
  "https://github.com/owner/repo/pull/7#issuecomment-123"}`. An artifact selector is
  `{"kind":"artifact_member","run_id":123,"artifact_id":456,"path":"proof.txt"}`.
  Selectors resolve only against the existing collector's authenticated retained
  records. Missing, ambiguous, incomplete or duplicate selections are errors.
- `verification_predecessor`: prior authenticated exact-subject event ID. Legacy
  terminal reports have a deterministic `verification-legacy-event/v1` identity
  containing repository, PR, head, merge, run ID and attempt. A caller-supplied
  hash without matching trusted history cannot establish causal currency.

An empty selector list covers code and original requests; it is not a claim that
previously required extra evidence was obtained. The existing collection plan
must carry its outstanding necessary selectors forward. This contract does not
infer necessity from every artifact or automatically discover a repair PR.
Explicit delivery relationships remain the delivery selector's responsibility.

The collector scans a separate authenticated conversation protocol inventory
before optional proof text/record rendering. Large optional comments and failed
inline-review rendering cannot hide a pending or incomplete event. Marker-only
conversation scanning continues to the API boundary within the existing page,
identity and page-stability limits. A genuinely incomplete conversation API
inventory returns the scoped `verification_event_history` retrieval requirement,
not authority to invoke another provider. Required proof selectors still resolve
their actual retained content; protocol records cannot substitute for proof.

Model invocations bypass the consumer's early coarse fingerprint. Actual
collection then precedes deduplication, including after rollout from an old
job-success fingerprint that never had a usable verifier decision. Checkbox
mode retains its existing fingerprint. A completed authenticated CONCERNS result
also deduplicates an unchanged event; unchanged failure is not a reason to buy
another opinion. A genuinely missing requested reviewer remains distinct through
`assessment_identity` (`mode`, requested `provider`, `model`, `model2`, `canonical`).
These are existing production evaluate/compare routes. Shadow and optional
advisory calls do not become new acceptance requirements.

Assessment identity mirrors arguments actually consumed by the authored command:
compare ignores the provider input and defaults its second model override to the
first; evaluate ignores the second-model input and omits `auto`/`github-models`
provider arguments. Those ignored inputs cannot purchase another identical
review. Historical and current metadata use the same normalization; actual
different effective reviewer requests remain distinct.

The collector retains `verification-event-manifest.json`. Trusted production
comments carry `verifier-event-state/v1` pending/incomplete records and the existing
`verifier-corpus-decision/v1` terminal record with the same event and assessment.
Incomplete records carry `retry_kind`, `retryable` and a bounded `failure_cause`:

- `known_no_evaluation`: a validated UNVERIFIABLE_INPUT payload establishes no
  evaluation, or the authoritative evaluator step never ran. Comparison requires
  every configured result slot. Only this kind permits a same-event retry.
- `recover_existing_evaluation`: retained validated output proves a provider
  evaluated the inputs; recover that result before considering another call.
- `uncertain_execution`: execution evidence is absent, malformed, conflicting
  or errored. Missing output and job success never establish no invocation.

The evaluator's exception path can emit `used_llm: false` after attempting a
provider call. Errored false-only payloads therefore remain uncertain. A matching
current incomplete state dominates same-attempt pending/terminal contradictions;
its original cause remains recorded. Pending or uncertain same-event assessment
state refuses evaluator re-invocation. Unrelated events and reviewer slots are
not dependencies of this guard.

Incomplete input or execution cannot produce a terminal PASS or consume the
consumer fingerprint. CI success alone cannot create acceptance. Model reports
retain their original verdicts; consumers must select applicable causal events
and preserve older results as history, including out-of-order arrivals.

Same-PR reusable jobs queue instead of cancelling an active evaluation. This
does not replace the caller's existing active/uncertain-effect exclusion or give
an incomplete request authority to replay an uncertain consequential action.

Pending records include `verifier-execution-binding/v1` naming the actual caller
workflow, verifier job, pending step and evaluator step. A later collection can
reconcile an abandoned pending request through the exact terminal run/attempt
and complete attempt-specific jobs inventory. The unique verifier job must show
the pending step succeeded and the expected evaluator step explicitly skipped;
every other present known evaluator step must also be skipped. The run is reread
to reject a concurrent rerun. The original pending marker stays immutable, and
the new input manifest retains the authenticated `verifier-no-evaluation-proof/v1`.
The same event and existing evaluator path can then retry without fabricating
fresh evidence. Active runs, missing/started steps, foreign identities, incomplete
API reads and legacy markers without the execution binding remain targeted
recovery work. Lost-runner age and generic job success never clear a pending
request. Existing output references are retained for collection when evaluation
may have started.

Focused checks:

```sh
node --test tests/scripts/test_verification_event.js .github/scripts/__tests__/agents-verifier-context.test.js
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/workflows/test_repeat_verification_lifecycle.py -q -o addopts=''
```
