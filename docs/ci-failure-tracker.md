# Gate CI Failure Tracker

`maint-46-post-ci.yml` listens to completed Gate runs. Its independent
`failure-tracker` job creates or updates `ci-failure` issues and publishes
`artifacts/ci_failures_snapshot.json`. The separate summary-recovery job can
skip after a successful summary without suppressing this tracker: a failed
upstream Python job still reaches failure tracking even if the summary succeeded.

The tracker checks out trusted `github.sha` with credential persistence disabled.
Only its job receives `issues: write`. Before writing it verifies the same-repository
PR identity, Gate workflow path, completed current run attempt, current PR head,
absence of a newer same-head Gate run, and the complete attempt-bound job list.
Fork, stale, incomplete and unbound events produce no issue writes. It never
executes code or scripts from the monitored PR or its artifacts.

## Failure and recovery

The existing signature remains the workflow slug plus failed job names and
conclusions in the issue title. This wiring does not introduce a different
signature/hash policy. `failure`, `timed_out`, `action_required` and
`startup_failure` jobs count as failures; skipped and neutral jobs do not.
Optional normalized stack tokens are diagnostic body text, not signature inputs.

An open exact-signature issue is updated first. Otherwise a recent issue in the
configured cooldown scope receives the recurrence instead of a duplicate issue.
Occurrence count, last seen, exact run/attempt/head and PR tags are updated even
when a comment is rate-limited. Replaying the last tracked run/attempt does not
increment occurrences. Cooldown uses paginated issue data, not environment
variable APIs or an artificial retry delay.

A healthy completed Gate closes its PR-tagged failure issues. An aggregate that
still tracks another PR stays open, with only the recovered PR tag removed.
The healthy path also checks the documented inactivity window for untagged issues; any remaining open or unverified tracked PR prevents inactivity-only closure; confirmed closed PR tags are retired. Repository-wide serialization uses `queue: max` to retain up to 100 pending jobs rather than replacing the sole pending event. Queue overflow remains a platform limit. Cancelled or
unknown outcomes do not establish recovery. Both valid failure and success paths
write the same snapshot schema, including `monitored_run` identity and current
open issues; snapshot writing runs in `finally` after a tracker action fails.
Upload uses the exact produced path and errors if a tracked run has no snapshot.
The artifact name includes the monitored Gate run and attempt.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `RATE_LIMIT_MINUTES` | Minimum interval between recurrence comments; counts still update | 15 |
| `STACK_TOKENS_ENABLED` | Include a diagnostic stack token | true |
| `STACK_TOKEN_MAX_LEN` | Maximum diagnostic token length | 160 |
| `STACK_TOKEN_RAW` | Preserve the unnormalized diagnostic token | false |
| `NEW_ISSUE_COOLDOWN_HOURS` | Append to a recent eligible issue instead of creating one | 12 |
| `COOLDOWN_SCOPE` | `global`, `workflow` or `signature` | global |
| `AUTO_HEAL_INACTIVITY_HOURS` | Inactivity required for the healthy-path scan | 24 |
| `DISABLE_FAILURE_ISSUES` | Skip failure issue create/update; retain snapshot | false |

The old environment-variable cooldown retry, occurrence-history table and
escalation descriptions were not implemented by these helpers; they are not
promised here. The separate signature-guard fixtures retain their own contract.

## Local simulation and controlled hosted receipt

From the repository root, run:

```bash
node --test .github/scripts/__tests__/maint-post-ci.test.js
```

The replay executes the actual JavaScript authored in Maint46's tracker step
against an in-memory GitHub API. It drives a successful summary with a failed
upstream leg, repeat failures, duplicate delivery, cooldown/comment throttling,
recovery and snapshots. Refusal cases cover fork/missing identity, current-head
drift, a newer Gate run, a different workflow and incomplete jobs. Another case
preserves other PRs in an aggregated issue during recovery.

Temporarily remove the `updateFailureTracker` call from the authored workflow
script: the replay must fail its real emitted-issue assertion. Restore the
workflow byte for byte and rerun successfully. No live issue is created by this
suite; `npm test` is unavailable in `.github/scripts/package.json`.

For a controlled hosted replay, dispatch the existing `Selftest CI` workflow at
the PR branch. Its `Gate tracker replay receipt` job runs the same authored replay
with `TRACKER_REPLAY_OUTPUT` and retains `failure.json`, `recovery.json`, raw
console output and `receipt.json` in the `gate-tracker-replay` artifact. The receipt
binds the workflow SHA and hosted run URL to the synthetic Gate run/head,
simulated issue writes and snapshots. This is hosted replay evidence, not a claim
that an unmerged workflow changed production issues. Actual production behavior
is observed only after merge and a qualifying Gate event.

The pinned actionlint versions predate GitHub's `concurrency.queue` property.
The existing actionlint allowlist therefore recognizes only its exact
unsupported-key diagnostic. An independent workflow-schema test validates every
root concurrency block: queue values must be `single` or `max`, and `max` cannot
cancel running jobs. Invalid values/combinations fail that check. All other
lint diagnostics and required CI remain enabled; no workflow or security check
is removed. See the [GitHub queue contract](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
