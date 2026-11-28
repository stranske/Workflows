# Keepalive Metrics Schema

The [Workflows keepalive loop](../../.github/workflows/agents-keepalive-loop.yml)
and [consumer Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
write one newline-delimited JSON (NDJSON) record from `finish` under the
Actions artifact `keepalive-metrics`. The file is `keepalive-metrics.ndjson`
and the upload retains it for 30 days. A workflow stopped before `finish`
can lack this artifact.

## Actions artifact record

| Field | Meaning |
| --- | --- |
| `pr_number` | Pull request number |
| `iteration_count` | Iteration reported by evaluation |
| `action`, `stop_reason` | Evaluator action and reason |
| `gate_conclusion` | Gate decision seen by evaluation |
| `tasks_total`, `tasks_completed` | Evaluation checklist counts |
| `duration_seconds` | Elapsed seconds between evaluation start and metric emission |

```json
{"pr_number":1234,"iteration_count":2,"action":"run","stop_reason":"ready","gate_conclusion":"success","tasks_total":14,"tasks_completed":6,"duration_seconds":481}
```

The counts describe the evaluator's snapshot. Consult the Automated Status
Summary, worker attempt and completion receipt for evidence recorded after the
round. The consumer's `metrics` job emits separate autofix evidence.

## Summary helper iteration record

The [summary helper](../../.github/scripts/keepalive_loop.js) also produces
`metrics_record_json` and can append it to its local NDJSON path. This record
has `pr_number`, `iteration`, `timestamp`, `action`, `error_category`,
`duration_ms`, `tasks_total` and `tasks_complete`. Its capability bundle
fields are `capability_bundle_ids`, `capability_bundle_hashes`,
`capability_gate_versions` and `capability_rejection_reasons`.
Use the Actions artifact schema above for downloads. The workflow uploads
that file before the summary helper can append its record.
