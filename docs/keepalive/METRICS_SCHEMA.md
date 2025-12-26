# Keepalive Metrics Schema

This document defines the structured metrics record written per keepalive
iteration. Records are newline-delimited JSON (NDJSON); one JSON object per
line.

## Fields

- pr_number: Integer PR number.
- iteration: Integer iteration count for the keepalive loop (1-based).
- timestamp: ISO 8601 UTC timestamp for when the metrics record was emitted.
- action: String describing the action taken during the iteration.
- error_category: String error classification or "none" when no error occurred.
- duration_ms: Integer duration in milliseconds for the iteration.
- tasks_total: Integer total tasks detected for the PR.
- tasks_complete: Integer completed tasks detected for the PR.

## Example Record

```json
{"pr_number":1234,"iteration":2,"timestamp":"2025-01-15T12:34:56Z","action":"retry","error_category":"none","duration_ms":4821,"tasks_total":14,"tasks_complete":6}
```
