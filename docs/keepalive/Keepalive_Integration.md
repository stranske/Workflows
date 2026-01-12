# Keepalive Integration Guide

This guide covers the keepalive configuration knobs that control timeouts and warning behavior.
Use it alongside `docs/keepalive/SETUP_CHECKLIST.md` for full setup steps.

## Repository Configuration

Set these repository variables to control default timeouts and warnings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `WORKFLOW_TIMEOUT_DEFAULT` | Default keepalive timeout (minutes) | `45` |
| `WORKFLOW_TIMEOUT_EXTENDED` | Timeout when `timeout:extended` label is present (minutes) | `90` |
| `WORKFLOW_TIMEOUT_WARNING_RATIO` | Warning threshold as a ratio (0-1) | `0.8` |
| `WORKFLOW_TIMEOUT_WARNING_MINUTES` | Warning threshold in remaining minutes | `5` |

Notes:
- `WORKFLOW_TIMEOUT_EXTENDED` is only used when the PR label `timeout:extended` is present.
- Warning thresholds are evaluated by ratio or remaining minutes. If either threshold is met,
  a warning is emitted in the keepalive summary and action logs.

## Workflow Inputs

Manual runs can override the configuration with workflow inputs:

- `timeout_minutes` - overrides the full timeout for the run.
- `timeout_warning_ratio` - overrides the warning threshold ratio.
- `timeout_warning_minutes` - overrides the warning threshold for remaining minutes.

Example workflow dispatch inputs:

```yaml
timeout_minutes: 75
timeout_warning_ratio: 0.8
timeout_warning_minutes: 10
```

## How Warnings Work

Keepalive computes elapsed time based on the workflow run start time (or an explicit `elapsed_ms`
input) and compares it to the resolved timeout.
Warnings appear when:

- elapsed time reaches 80% of the configured timeout, or
- remaining time drops to 5 minutes or less.

The summary comment and action logs include the percentage consumed and remaining minutes.
