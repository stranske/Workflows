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
updates those PRs in place. Before changing a head it disables auto-merge,
converts the PR to draft, and applies `sync:delivery-staging`; an exact
base/tree no-op preserves the existing lifecycle instead of restarting review.

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
`dev-tool-sync`), `observed_at`.

Exception fingerprints used for local Codex handoff include repository, PR
number, head SHA, and active review-thread identity. `updated_at` is metadata
only and must not create a new fingerprint or claim generation.

## Local-consumer migration (operator follow-up)

Repository automation publishes the remote handoff schema above. Updating any
local watcher / opener / closer consumer to read `delivery_handoffs` (instead of
re-deriving merge/close policy) is an **operator follow-up**, not additional
repository implementation work for this contract.
