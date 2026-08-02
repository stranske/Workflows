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
