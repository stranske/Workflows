# Sync/Dependency Campaign Contract

The durable coordination surface for generated dependency and consumer-sync
work is the campaign issue, not an individual generated pull request. A pull
request is a leased delivery attempt and must carry the
`sync-pr-delivery-record:v1` marker (schema `sync-pr-delivery-record/v1`) with its durable issue, plan, generation,
repository, desired tree hash, source commit, expiry, and lineage.

Maint 71 is the sole merge/close reconciler. It applies the same contract to
both `sync/workflows-*` consumer-sync branches and
`deps/sync-dev-versions-*` shared dev-tool propagation branches:

- current attempts with passing required checks and no active review threads
  may be merged;
- pending checks, active reviews, repository-local failures, and shared-source
  failures retain a precise owner and next command;
- expired or superseded attempts are closed rather than revived; and
- legacy attempts without a record require an explicit, one-time provenance
  decision before any merge.

Consumer sync uses two stable lanes: `sync/workflows-candidate` for configured
canaries and `sync/workflows-delivery` for promoted non-canaries. Maint 68
updates those ready-for-review PRs in place. Before changing a head it disables
auto-merge and applies `sync:delivery-staging` without changing readiness; an
exact base/tree no-op preserves the existing lifecycle instead of restarting review.

Maint 71 advances a stable PR from `staging` to `reviewing` and finally
`sealed`. Reviewer capacity is explicitly bounded: one configured reviewer
response is sufficient after seven minutes, all-capacity-unavailable may
degrade after that quiet period, and a zero-response window degrades after
fifteen minutes. None of these paths permits an active non-outdated review
thread. Sealing binds the record to the exact head and triggers a fresh Gate via
`sync:delivery-ready`. The Gate summary rejects an unsealed stable delivery and
the shared merger guard rejects `sync:delivery-staging`; only Maint 71 may
override that label after independently verifying the seal, checks, head, and
live threads.

For the candidate lane, Maint 71 must upload a complete, green, review-clear
`sync-canary-evidence-premerge` artifact before it merges any candidate PR.
Lifecycle transitions may occur before that artifact because they are
reversible and produce the exact-head evidence; the irreversible merge may not.
Operators and local closers must not call `gh pr merge` or arm auto-merge on
stable sync PRs directly. This ordering keeps a GitHub
`action_required` pre-job approval hold or an artifact failure recoverable
instead of consuming the only evidence-bearing PRs.
Maint 71 derives candidate scope from `config/consumer_sync_canaries.json`; it
must not scan the complete consumer registry in candidate mode because an
unrelated non-canary delivery branch cannot be allowed to block canary evidence.
Every generated delivery must also remain on one exact head for at least seven
full minutes. Maint 71 re-reads that head and live non-outdated review threads
immediately before its merge call; a changed head restarts the window.
Candidate mode is normalized from workflow-call, manual, and repository-dispatch
selectors. The executor refuses to merge a selected stable candidate unless
the same job's evidence-validation and pre-merge artifact steps both succeeded;
an unscoped scheduled run therefore cannot merge candidates implicitly.

Maint 82 (`maint-82-sync-dependency-campaign.yml`) owns the durable campaign
state and only requests local agent work when an actionable exception
fingerprint materially changes. Timestamps alone do not constitute new work.
Local watchers consume the normalized handoff record and do not independently
decide merge or close disposition.

The same marker is the timed continuation queue. Maint 71 classifies every
handoff as `transient`, `actionable`, or `terminal`, names its candidate,
delivery, or dev-tool lane, and records an immutable `resume_after` for
transient states. Maint 82 checks that queue every ten minutes and dispatches at
most one due run per lane, suppressing a new candidate while a promoted delivery
is active. Consumer `agents-81-gate-followups.yml` sends the event-driven wakeup
when a generated branch's Gate finishes; the timed queue covers quiet-period
expiration and lost/delayed events. Pending checks and review windows therefore
advance automatically, while failed checks and review findings keep their named
owner instead of being disguised as timer retries.

Every transient classification has a non-zero retry delay and becomes eligible
only after that due time has passed. Dev-tool wakes use the explicit `dev-tool`
selector, which reconciles the newest dev-tool PR per registered non-admin repo
without allowing a newer workflow-sync PR to hide it.

A stable candidate that falls behind its consumer base is also transient.
Maint 71 returns it to staging and dispatches one deduplicated, no-filter Maint
68 `phase=canary` refresh; it never sends non-canaries through that phase and it
will not start the refresh while a canary or promotion run is active. The timer
queue retains the candidate continuation if that dispatch is lost.

Promotion binds the exact canary evidence into every Workflows-App-signed
delivery commit. If a stable delivery falls behind during review, Maint 71
restages it, extracts and validates that signed evidence against the delivery
plan, and replays Maint 68 `phase=promote` with `delivery_scope=auto`. Mutable
consumer PR text is not an evidence source. Missing or unverifiable signed
evidence is actionable and fails closed instead of becoming a retry loop.

After a candidate-selector run has complete same-plan evidence and every
configured candidate was merged or recovered, Maint 71 passes that exact JSON
to Maint 68 `phase=promote`. Maint 68 in turn dispatches the delivery selector
after writing non-canary PRs. Neither chain permits an explicit non-canary repo
through `phase=canary`, and `stranske/Collab-Admin` is excluded from default
fleet reconciler targets. Its administration-surface delivery may be processed
only by a `workflow_dispatch` Maint 71 request whose normalized inputs are
exactly `repos=stranske/Collab-Admin` and `active_sync_hash=delivery`; it never
contributes to candidate or campaign evidence. Scheduled, repository-dispatch,
workflow-call, mixed-repository, unscoped, candidate, campaign, and dev-tool
requests continue to exclude it.

An active review thread remains a hard merge block. The bounded exception is an
explicit `workflows-sync-review-resolution/v1` proof supplied to Maint 71. It
must name one active thread, PR, exact head, substantive reason, Workflows PR or
commit evidence URL, and merged Workflows source-fix SHA. Maint 71 verifies the
authenticated dispatcher, unchanged head, active thread, and that the fix is an
ancestor of the delivery's recorded source commit before resolving that thread.
General source ancestry, a newer wave, or passing CI alone never clears review
debt.

Proof application is a dedicated resolution-only prepass: it may resolve only
the named verified thread and cannot merge, close, restage, or seal a PR. Maint
71 then performs its read-only evidence pass and explicitly validates that the
persisted premerge artifact contains every configured canary on one green,
review-clear plan. Upload success without complete evidence cannot authorize a
candidate merge; normal lifecycle transitions may still advance for the next
pass.

## Remote delivery handoff schema (`workflows-generated-delivery-handoff/v1`)

Maint 71 emits normalized result records (artifact + best-effort
`repository_dispatch` payload field `delivery_handoff_records`). Maint 82
persists them in the campaign marker as `delivery_handoffs`.

Required fields:

| Field | Meaning |
| --- | --- |
| `schema` | Always `workflows-generated-delivery-handoff/v1` |
| `repository` | `owner/repo` for the generated PR |
| `pr` | Generated PR number |
| `head_sha` | Head commit SHA observed at reconciliation |
| `delivery_generation` | Lease/delivery generation from the PR record |
| `disposition` | One of: `current`, `awaiting-checks`, `review-blocked`, `repo-local-failure`, `shared-source-failure`, `superseded`, `expired`, `owner-decision` (terminal rewrite may set `merged` / `closed`) |
| `blocker_owner` | Exact owner for the next action (`maint-71`, `ci`, `closer`, `repo`, `source`, …) |
| `next_command` | Exact resume command/token for opener/closer |
| `check_state` | Check summary (`ready`, `checks_pending`, `checks_failed`, …) |
| `review_state` | Review summary (`clear`, `blocked`, …) |

Optional fields retained when present: `branch`, `lane` (`sync` /
`dev-tool-sync`), `observed_at`, and `continuation` (`class`, `lane`, `reason`,
`resume_after`).

Exception fingerprints used for local Codex handoff include repository, PR
number, head SHA, and active review-thread identity. `updated_at` is metadata
only and must not create a new fingerprint or claim generation.

## Local-consumer migration (operator follow-up)

Repository automation publishes the remote handoff schema above. Updating any
local watcher / opener / closer consumer to read `delivery_handoffs` (instead of
re-deriving merge/close policy) is an **operator follow-up**, not additional
repository implementation work for this contract.
