# Keepalive Integration Guide

This guide covers the keepalive configuration knobs that control timeouts and warning behavior.
For installation and credentials, use the [consumer setup checklist](SETUP_CHECKLIST.md).

For the hosted loop and comment activation, see [Keepalive approaches](Keepalive_Approaches.md).

## Repository Configuration

Set these repository variables to control default timeouts and warnings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `WORKFLOW_TIMEOUT_DEFAULT` | Default keepalive timeout (minutes) | `45` |
| `WORKFLOW_TIMEOUT_EXTENDED` | Duration when the PR has `timeout:extended`, in minutes | Twice the resolved default, normally `90` |
| `WORKFLOW_TIMEOUT_WARNING_RATIO` | Warning threshold as a ratio (0-1) | `0.8` |
| `WORKFLOW_TIMEOUT_WARNING_MINUTES` | Warning threshold in remaining minutes | `5` |

Notes:
- `WORKFLOW_TIMEOUT_EXTENDED` is only used when the PR label `timeout:extended` is present.
- Warning thresholds are evaluated by ratio or remaining minutes. If either threshold is met,
  a warning can appear in the keepalive summary and action logs.

## Manual runs

The [Workflows loop](../../.github/workflows/agents-keepalive-loop.yml) and
[consumer Gate Followups](../../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml)
use the same [timeout resolver](../../.github/scripts/timeout_config.js). The
[summary helper](../../.github/scripts/keepalive_loop.js) can read repository
variables through the Actions API. Set them in the repository running the
workflow. These values feed summary diagnostics. The workflow job and the
agent CLI have their own execution limits.

## How Warnings Work

Keepalive computes elapsed time from the workflow run start time and compares it to the resolved timeout.
By default, warnings appear when:

- elapsed time reaches 80% of the configured timeout, or
- remaining time drops to 5 minutes or less.

The summary comment and action logs include the percentage consumed and remaining minutes.
