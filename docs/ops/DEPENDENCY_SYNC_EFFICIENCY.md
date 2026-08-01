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
  threads, or check-failure clusters rather than observation timestamps.

`stranske/Collab-Admin` is reported separately and excluded from primary fleet
SLOs because its generated work originates in the administration surface.

## Advisory thresholds

| Signal | Advisory threshold |
| --- | ---: |
| Generated PRs/week | ≤ 40 |
| Stale or replacement PR rate | < 5% |
| Avoidable replacements per repository/batch | 0 |
| Distinct agent-exception episodes/week | ≤ 5 |

Security-bypass PRs remain visible in the lane report. They are not treated as
routine cadence violations merely because they bypass the weekly update window.

## Evidence and retention

The workflow uploads JSON and Markdown artifacts for every run. Its current
collector deliberately reads the latest 100 updated PRs and workflow runs per
repository, applies an explicit trailing seven-day reporting window, and writes
`history_complete: false` with that limitation named in every report; rates are
never presented as complete historical truth when the input is bounded.

Weekly `created` / `merged` / `closed` counts use event timestamps inside the
reporting window. The Markdown report always shows rate numerator/denominator
evidence plus any avoidable-replacement repository/batch keys that drive a
breach.

The dedicated durable tracker
([#2897](https://github.com/stranske/Workflows/issues/2897)) receives a comment
only when the report's material-evidence fingerprint changes. Health 83 must not
post onto `#1836` (Sync/Dependabot campaign queue). A timestamp-only refresh
therefore does not create another tracker comment or agent handoff.
