# Keepalive Metrics Schema

This document defines the structured metrics record written per keepalive
iteration. Records are newline-delimited JSON (NDJSON); one JSON object per
line.

## Record Types

The metrics log supports two record types:

- Keepalive iteration records (`metric_type: "keepalive"` or omitted)
- Post-merge summary records (`metric_type: "post-merge"`)

## Keepalive Iteration Fields

- pr_number: Integer PR number.
- iteration: Integer iteration count for the keepalive loop (1-based).
- timestamp: ISO 8601 UTC timestamp for when the metrics record was emitted.
- action: String describing the action taken during the iteration.
- error_category: String error classification or "none" when no error occurred.
- duration_ms: Integer duration in milliseconds for the iteration.
- tasks_total: Integer total tasks detected for the PR.
- tasks_complete: Integer completed tasks detected for the PR.
- capability_bundle_ids: Array of applied `capability-bundle/v1` IDs.
- capability_bundle_hashes: Array of applied bundle content hashes.
- capability_gate_versions: Array of gate refs and playbook refs attached by applied bundles.
- capability_rejection_reasons: Array of deterministic reasons bundles were not applied.
- metric_type: Optional string. When present, set to `"keepalive"`.

## Post-Merge Summary Fields

- metric_type: String literal `"post-merge"`.
- pr_number: Integer PR number.
- timestamp: ISO 8601 UTC timestamp for when the summary record was emitted.
- merged_at: ISO 8601 UTC timestamp for when the PR was merged.
- iteration_count: Integer total keepalive iterations for the PR.
- tasks_total: Integer total tasks detected for the PR.
- tasks_complete: Integer completed tasks detected for the PR.
- completion_rate: Float between 0.0 and 1.0 representing task completion.
- human_interventions: Integer count of human interventions (comments, manual edits).

## Example Record

```json
{"pr_number":1234,"iteration":2,"timestamp":"2025-01-15T12:34:56Z","action":"retry","error_category":"none","duration_ms":4821,"tasks_total":14,"tasks_complete":6,"capability_bundle_ids":["keepalive/static-spa"],"capability_bundle_hashes":["sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],"capability_gate_versions":["frontend_verify@1","docs/keepalive/KEEPALIVE_TROUBLESHOOTING.md"],"capability_rejection_reasons":[]}
```

## Example Post-Merge Record

```json
{"metric_type":"post-merge","pr_number":1234,"timestamp":"2025-01-16T09:00:00Z","merged_at":"2025-01-16T08:55:12Z","iteration_count":3,"tasks_total":14,"tasks_complete":14,"completion_rate":1.0,"human_interventions":2}
```
