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
  Explicit comment selectors may also name a source issue already bound by the
  acceptance-source collector. The collector fetches that exact comment by ID,
  checks its repository/thread, actor ID and timestamps, and retains its full
  bounded body before optional PR chatter. Missing or oversized necessary text
  remains an explicit retrieval failure. Its body participates in event identity.
  Historical request revisions remain evidence of historical scope, not current
  operating instructions; later authenticated user directions still take precedence.
  A comparison baseline adds `"evidence_role":"comparison-baseline"` and
  `"compared_paths":["src/target.py"]` to an artifact-member selector. The collector
  authenticates the same-repository completed run, its true ancestor relationship
  to the evaluated merge, and identical bounded file bytes at both commits for
  every named path (at most eight distinct paths per collection). It retains Git
  blob IDs and SHA-256 identities in the material binding. This proves only those paths are unchanged; it neither makes the old
  run current CI nor establishes equivalent requirements or acceptance.
  Explicit selected run and artifact IDs use the existing finite material-selector
  bound independently of optional discovery counts. If a selected ID is beyond a
  bounded artifact listing, the collector reads its metadata directly and checks
  its exact run, repository, head and SHA-256 archive digest before extraction.
  An incomplete optional listing stays incomplete; resolving one selected ID does
  not certify undiscovered siblings. Archive, extraction and transport byte limits
  are unchanged. Selected artifacts and members are retrieved without reading
  oversized unselected siblings. The full bounded inventory retains those
  siblings as `unselected`, never complete or reviewed. Their availability gaps
  can be omitted only when the existing evidence policy permits that channel to
  be optional. Required selected truncation, unsafe members, duplicate identities
  and integrity failures remain blocking. Selected proof remains a complete
  required builder section through ordinary prompt fitting and native count
  admission, even when optional enrichment is omitted. These character budgets
  bound optional packing, not necessary proof or model capacity. A complete single
  changed-file patch likewise gets its own chunk when it exceeds the rough group
  budget; the shared native counter must admit the actual full request before any
  generation. Native overflow or missing mandatory proof cannot earn review credit.
  Descriptive evidence sentences do not inherit an unrelated later sentence's
  mandate; abbreviation/initialism periods retain their governing delivery clause.
  The existing fitter measures necessary evidence before optional enrichment.
  Necessary selected proof above its soft bound requires native admission too,
  even with a small diff; omitted optional history alone does not change ordinary
  bounded legacy transport. Original upload/comment duties are not waived by selection. The existing mandatory-duty policy is channel-wide: a
  specific selected upload does not automatically settle other unselected artifact
  obligations; that conservative limitation remains explicit.
- `verification_predecessor`: prior authenticated exact-subject event ID. Legacy
  terminal reports have a deterministic `verification-legacy-event/v1` identity
  containing repository, PR, head, merge, run ID and attempt. A caller-supplied
  hash without matching trusted history cannot establish causal currency.
  A changed-material event can also follow a latest authenticated incomplete
  event classified `known_no_evaluation` by the existing execution classifier.
  The exact subject, run/attempt, canonical assessment and matching pending-step
  execution binding must agree. Pending, uncertain, malformed, conflicting or
  newer work cannot grant this authority. The old incomplete event and its parent
  remain unchanged; this adds a real successor instead of forking its earlier
  semantic ancestor. A false-only payload or job success is not this proof.
  Repeating that already-created event retains its same authenticated predecessor;
  its newer records are not a competing material branch. Every retained child
  record must agree on that edge. Earlier unresolved executions still require
  recovery through the existing Actions reconciler for each authenticated older
  pending attempt. Only fresh skipped-evaluator proof discharges that attempt
  within the current collection; retained comments and history stay unchanged.
  Latest pending work uses the normal execution reconciliation, and
  completed exact-event work remains deduplicated even after a later no-evaluation
  attempt. Neither a new nonce nor
  omitting the original predecessor grants permission for another model call.

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

Evaluate and compare validate results against the authoritative `.workflows-lib`
checkout, even when the caller contains an older `scripts` package. Each normal
publication joins the exact retained payload hash/byte count to its mode-specific
execution receipt, repository and run/attempt. The outgoing report verdict, corpus
marker, terminal event and provisional PASS settlement use this same admission.
An invalid receipt cannot publish a raw PASS marker; an already present marker in
model report text is removed before the current job's annotation is rebuilt.
Original payloads, receipts and previously published history remain unchanged.
Semantic comparison joins report rows to the authenticated judge/package cell
matrix; it does not require one row per provider. Legacy direct comparisons retain
their existing configured-slot completeness checks.
A retained usable model response with a failed wrapper is recovery input, never
permission to invoke the provider again. Revalidation alone is not publication
authority or a replacement execution receipt.

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
every other present known evaluator step must also be skipped. The exact attempt
endpoint authenticates the original pending attempt even after a rerun exists.
Every newer terminal attempt is inspected separately and must affirmatively show
the expected evaluator skipped; missing or started steps remain unresolved.
At most ten contiguous attempts and ten total jobs pages are inspected. Both
exact attempt metadata and latest-run metadata are reread to reject concurrent
changes. Only the authenticated hosted collector may exempt its own current
attempt while it is still collecting before pending/evaluator execution. That
exception requires its actual platform repository, workflow reference, run and
attempt; competing or started attempts cannot use it. Native callers have no
self-collection exception. The original pending marker stays immutable, and
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

## Input-repair provenance for results retained before the marker existed

Changed-input recovery of a retained provider outcome that included
`UNVERIFIABLE_INPUT` needs one authenticated `verifier-input-repair/v1` marker.
Runs that finished before the producer emitted it (#4231, #4235, #4238) have none.
`verification_provenance` publishes that marker for such a run and nothing else.
The source owner must dispatch it before the original `comparison-results-<run>`
or `evaluation-results-<run>` artifact expires. Retention is at most seven days
after the original run. After expiry, the dispatch is rejected and the marker
cannot be published:

```sh
gh workflow run agents-verifier.yml -f pr_number=<PR> -f mode=<original mode> -f provider=<original provider> \
  -f verification_provenance='{"run_id":<id>,"run_attempt":<n>,"artifact_id":<id>}'
```

The input takes the same exact selector as `verification_recovery`, is rejected when
combined with `verification_recovery`, `verification_event`, `verification_material`,
`verification_predecessor` or `evidence_profile: expanded`, and must restate the
original assessment (`mode`/`provider`/`model`/`model2`). It runs in its own
`input-repair-provenance` job: the `verifier` job, providers, provider secrets,
native capacity and shadow judges are all skipped.

The job reads the full PR comment history through the Actions API and requires, for
that exact run and attempt, one authenticated `github-actions` incomplete state with
`failure_cause: retained_provider_evaluation`, `retryable: false` and the same
canonical assessment, and no terminal decision. Newer or malformed canonical
work blocks it (the retained-recovery ordering guard). It then reuses
`acquireRetainedExecution` (run, attempt, job steps, artifact digest, helper checkout,
canonical origin) and strictly reads the archive: the original event manifest must
rebind the event, request and material digests, and the execution receipt must join the
result bytes and run/attempt. Every provider slot must have run, none may have errored,
and at least one must report `UNVERIFIABLE_INPUT`.

Label-triggered (`pull_request_target`) originals report the PR head as the run head,
which a squash merge leaves off the default branch. This operation therefore binds such
a run through its merged pull request (head, canonical merge commit, post-merge start);
the existing retained-revalidation path keeps its stricter check.

The only write is one comment from the Actions token carrying the marker
(`verification_event`, assessment, original material, result/receipt digests and copied
provider verdicts) plus a separate non-authoritative `verifier-input-repair-publication/v1`
line with the publishing run. Publisher lineage stays outside the marker so a repeat is
byte-identical: an exact repeat posts nothing, any different marker for the same attempt
fails closed, and a lost POST response is reconciled by reading, never by a second write.
No `verifier-event-state` or terminal record is written, so the original attempt remains the
latest canonical work. The marker grants no verdict, acceptance or same-event retry; a later
changed-input admission still has to collect sufficient, demonstrably changed material.

## Provider-free retained-output recovery

`verification_recovery` is an optional JSON string containing exactly positive
integer `run_id`, `run_attempt`, and `artifact_id` selectors. It accepts no
caller-supplied digests or verdict. Its presence disables all provider, native
capacity, provider-secret and shadow execution, even if recovery fails.

The existing collector authenticates the completed source attempt and artifact
through GitHub Actions, including repository/workflow/job/checkout origin and
archive digest. Recovery requires complete original result, receipt, input
manifest, context, diff and event bytes, plus the same freshly collected request,
required material, revision and assessment. Missing or changed evidence stops
recovery; it never falls through to a new model call. A prior exact terminal
result, including NON_PASS under an older validator, does not suppress this
explicit provider-free revalidation. Its authenticated source and recovery-key
history guard still apply; ordinary model requests remain completion-deduplicated.

Original files and invalid receipts remain unchanged in the retained source
archive. A new typed revalidation receipt records the original run/artifact and
hashes, the current validator, and `provider_generation_performed: false`.
The normal admitted report, event, unified verdict and source-closure gates
consume that receipt. A later applicable assessment prevents stale publication;
exact duplicate recovery and uncertain comment writes are reconciled by
identity before another publication. Recovery does not rewrite an event's
predecessor or turn old advisory output into current acceptance authority.

Recovery lifecycle states carry the stable recovery key. A failed read or validation
can retry only when the publisher was skipped or positively remained before its POST.
A lost terminal state uses the existing Actions execution reconciler to prove that
publication never started; different attempts of the same run remain distinct.
An uncertain POST stays fenced unless an admitted matching public report is observed.
If that report's lifecycle was interrupted, fresh provider-free revalidation can
complete it while retaining the original records; an already-completed key is deduplicated.


### Explicit required comment proof

A `verification_material` comment selector is required evidence, whether it names
the target PR or an already authenticated linked issue. Fetch that exact comment
before optional history fills its budget, validate its repository/thread/ID,
author and timestamps, and retain its complete body with provenance. The normal
conversation/event inventory still runs; a selected record that changes during
that scan is an input-integrity gap, including bot-authored records whose new
body would otherwise be filtered as chatter.

The producer separates selected comment proof from optional comment history.
Prompt fitting preserves the entire selected section even when it exceeds the
optional-enrichment budget; the existing native whole-request counter admits or
refuses the resulting request. Place it before legacy optional section headings
so older channel fitters also retain the mandatory prefix. A legacy mixed section
that identifies selected required comments stays whole during fitting, including
when the original request names no evidence channel. Refresh through the normal
producer to separate that old section's required proof from optional history;
until then the unchanged native counter must admit its complete retained bytes.
These are input guarantees, not evidence of acceptance or permission to replay
an existing evaluation.
