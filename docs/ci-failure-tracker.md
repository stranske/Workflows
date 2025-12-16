# CI Failure Tracker (Phase-2 Enhancements)

This document summarises the behaviour and configuration of the enhanced failure tracking workflow.

## Overview
The Gate summary job now owns the failure-tracker logic and listens to completed runs of the Gate workflow. The legacy `maint-47-check-failure-tracker.yml` workflow has been retired after delegation proved stable. Within the consolidated summary job, a dedicated `failure-tracker` step executes on qualifying failures and:

1. Enumerates failed jobs and the first failing step.
2. Optionally extracts a stack token (first exception or error line) per failed job.
3. Builds a deterministic signature: `workflow|sha256(job::step::stackToken...)[:12]`.
4. Opens or updates a single GitHub Issue per signature (labels: `ci-failure`, `ci`, `devops`, `priority: medium`).
5. Maintains metadata header: Occurrences, Last seen, Healing threshold.
6. Appends a failure comment (rate-limited) with job + stack token tables.
7. On successful runs, scans for inactive issues and auto-closes those with no reoccurrence for the configured inactivity window.

## Configuration (Environment Variables)
| Variable | Purpose | Default |
|----------|---------|---------|
| `RATE_LIMIT_MINUTES` | Minimum minutes between new comments for same issue | 15 |
| `STACK_TOKENS_ENABLED` | Toggle stack token hashing (`true`/`false`) | true |
| `STACK_TOKEN_MAX_LEN` | Max chars retained from a stack/error line | 160 |
| `STACK_TOKEN_RAW` | Skip stack token normalisation when `true` | false |
| `AUTO_HEAL_INACTIVITY_HOURS` | Hours of stability before success path auto-heal closes issue | 24 |
| `FAILURE_INACTIVITY_HEAL_HOURS` | (Reserved) Close during failure path if inactive for this many hours | 0 (disabled) |
| `NEW_ISSUE_COOLDOWN_HOURS` | Cooldown window before creating *new* failure issues | 12 |
| `COOLDOWN_SCOPE` | Which issue to target during cooldown (`global`, `workflow`, `signature`) | global |
| `COOLDOWN_RETRY_MS` | Delay before retrying the cooldown append logic | 3000 |
| `DISABLE_FAILURE_ISSUES` | If `true`, skip failure issue create/update (summary only) | false |
| `OCCURRENCE_ESCALATE_THRESHOLD` | Escalation trigger once occurrences reach this count | 3 |
| `ESCALATE_LABEL` | Label applied during escalation | `priority: high` |
| `ESCALATE_COMMENT` | Custom escalation comment body | (empty) |

## Signature Evolution
- Phase-1: job + first failing step.
- Phase-2: adds first stack/error line token (or `no-stack` / `stacks-off`).

## Cooldown & Rate Limiting
A newly-detected signature that would otherwise open a new issue first checks for recent failures within the `NEW_ISSUE_COOLDOWN_HOURS` window. When the cooldown is active, the run appends a comment to the selected issue instead of opening a duplicate. The default twelve-hour window balances duplicate suppression with timely visibility of unrelated failures.

A run comment is additionally suppressed if:
- The run URL already appears in an existing comment, OR
- The last comment is younger than `RATE_LIMIT_MINUTES`.

## Legacy PR Exclusions
Gate runs that originate from historical pull requests #10 and #12 are explicitly marked by the Gate summary job with `failure_tracker_skip = true`. When that flag is set the failure-tracker path, success auto-heal, and consolidated PR comment jobs all short-circuit. This prevents the legacy threads from accumulating duplicate bot comments while allowing all modern PRs to benefit from the unified tracker flow.

## Auto-Heal (Success Path)
On any successful monitored workflow run, open `ci-failure` issues are scanned. If `Last seen` is older than `AUTO_HEAL_INACTIVITY_HOURS`, the issue is commented on and closed.

## Escalation Threshold
Once an issue records its third occurrence (`OCCURRENCE_ESCALATE_THRESHOLD`), the workflow ensures the escalation label (`priority: high` by default) is applied and posts a single escalation comment. Earlier occurrences retain the medium-priority label so responders can distinguish first-time breakages from persistent regressions.

### Label inventory check
The repository currently exposes the following triage labels that ship with the workflow: `ci-failure`, `ci`, `devops`, and `priority: medium`. The escalation label (`priority: high` by default) is created automatically on demand. If any label gets renamed in the future, update the defaults in the workflow to match the new taxonomy so issues continue to aggregate correctly.

## JSON Snapshot Artifact
Both the failure and success paths upload the `ci_failures_snapshot.json` artifact so downstream automation has a single canonical payload to consume regardless of Gate outcome. The artifact contains an array of current open failure issues (number, occurrences, last_seen, timestamps). Use this for dashboards or external monitoring.

## Occurrence History
Each failure issue maintains an internal, capped (10 rows) occurrence history table between HTML comment markers:
```
<!-- occurrence-history-start -->
| Timestamp | Run | Sig Hash | Failed Jobs |
|---|---|---|---|
| 2025-09-23T12:34:56Z | run link | a1b2c3d4e5f6 | 2 |
<!-- occurrence-history-end -->
```
New failures prepend a row; table truncated at 10 to keep issues readable.

## Deterministic Signature Self-Test
Utility script: `tools/test_failure_signature.py`

Example:
```bash
python tools/test_failure_signature.py \
	--jobs '[{"name":"Tests","step":"pytest","stack":"ValueError: boom"}]' \
	--expected 0123456789ab
```
Integrate into local pre-flight checks to ensure signature algorithm adjustments are deliberate.

## Signature Guard Workflow
Workflow: `health-43-ci-signature-guard.yml` runs on pushes / PRs and validates that a canonical fixture (`.github/signature-fixtures/basic_jobs.json`) hashes to the expected value stored in `basic_hash.txt`. Any intentional algorithm change should update both fixture and expected hash in the same commit.

## Manual Self-Test
You can manually validate behaviour:
1. Dispatch `Maint 90 Selftest` (will create a failing issue).
2. Rerun it but edit the `maint-90-selftest.yml` workflow to succeed (or manually re-run jobs) to test auto-heal logic after adjusting `INACTIVITY_HOURS`.

## Local Simulation Harness
For a fast feedback loop without touching GitHub, run `node tools/simulate_failure_tracker.js`. The harness lifts the tracker script from the Gate summary job and replays three sequential failures against an in-memory stub of the GitHub API. It asserts that:

- The tuned defaults (12-hour cooldown, three-occurrence escalation) are honoured.
- Issues aggregate signatures instead of spawning duplicates across the cooldown window.
- The escalation label and comment appear only after the third occurrence while the base triage labels remain intact.

Use this script whenever adjusting cooldown, label, or escalation logic to confirm the behaviour before pushing workflow changes.

## Future Extensions
- Persist aggregated metrics (failure frequency) as JSON artifact.
- Add PR comment summary for new signatures encountered in a PR context.
- Integrate stack token similarity clustering for noisy crash variants.


## Maintenance Checklist
- If new workflows should be monitored, add their names to the `workflows:` array under the `workflow_run` trigger.
- Keep labels consistent with project taxonomy.
- When refining stack heuristics, ensure deterministic fallback values to preserve signature stability.
