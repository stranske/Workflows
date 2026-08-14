# Dependency/sync maintenance efficiency

Health 83 publishes an advisory weekly report for dependency-bot, consumer-sync,
and dev-tool-sync work. It is a cost-control signal, not a merge gate. The first
four complete weeks are a baseline period; any change from advisory to blocking
requires an explicit repository decision.

## Measures

The report records the numerator, denominator, lane classification, and collection
limit for each measure:

- created, merged, closed, stale, and replacement generated PRs;
- source-change-to-consumer-PR amplification and Actions runs per source change;
- avoidable replacement attempts per repository/batch; and
- distinct agent-exception fingerprints, based on changed heads, active review
  threads, or check-failure clusters rather than observation timestamps;
- force-push, draft/ready, review-request, and review-submission events on the
  stable `sync/workflows-candidate` and `sync/workflows-delivery` PRs; and
- review-start-to-seal and observed-head-to-seal convergence from each stable
  PR's `sync-pr-delivery-record:v1` lifecycle marker.

`stranske/Collab-Admin` is reported separately and excluded from primary fleet
SLOs because its generated work originates in the administration surface.

## Advisory thresholds

| Signal | Advisory threshold |
| --- | ---: |
| Generated PRs/week | ≤ 40 |
| Stale or replacement PR rate | < 5% |
| Avoidable replacements per repository/batch | 0 |
| Distinct agent-exception episodes/week | ≤ 5 |
| Force pushes per stable sync PR | ≤ 1 |
| Ready-for-review transitions per stable sync PR | ≤ 1 |
| Median review-start-to-seal time | ≤ 30 minutes |

Security-bypass PRs remain visible in the lane report. They are not treated as
routine cadence violations merely because they bypass the weekly update window.

## Evidence and retention

The workflow uploads JSON and Markdown artifacts for every run. Its collector
completely paginates PRs and workflow runs for the explicit trailing seven-day
reporting window and completely paginates timeline events for each stable sync
PR observed in that window. It writes `window_complete: true` only when every
stable-PR timeline read succeeds. All-time history remains deliberately
uncollected, so every report also writes `history_complete: false`; rates are
never presented as complete historical truth outside the stated window.
Malformed lifecycle timestamps in a PR body are treated as unavailable timing
evidence rather than aborting the weekly report.

Weekly `created` / `merged` / `closed` counts use event timestamps inside the
reporting window. The Markdown report always shows rate numerator/denominator
evidence plus any avoidable-replacement repository/batch keys that drive a
breach. The stable-delivery table makes repeated head rewrites and repeated
draft-to-ready review cycles visible per PR instead of treating an updated PR as
one inexpensive delivery attempt.

The dedicated durable tracker
([#2897](https://github.com/stranske/Workflows/issues/2897)) receives a comment
only when the report's material-evidence fingerprint changes. Health 83 must not
post onto `#1836` (Sync/Dependabot campaign queue). A timestamp-only refresh
therefore does not create another tracker comment or agent handoff.
