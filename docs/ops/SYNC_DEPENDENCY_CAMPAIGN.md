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
- pending checks, active reviews, and repository-local failures retain a
  precise owner and next command;
- expired or superseded attempts are closed rather than revived; and
- legacy attempts without a record require an explicit, one-time provenance
  decision before any merge.

Maint 82 owns the durable campaign state and only requests local agent work
when an actionable exception fingerprint materially changes. Timestamps alone
do not constitute new work. Local watchers consume the normalized handoff
record and do not independently decide merge or close disposition.
