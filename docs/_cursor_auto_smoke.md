# Cursor Auto-Model Smoke Test

Throwaway PR verifying that the keepalive **cursor** lane now runs `--model auto` (Cursor's free
Auto bucket) after PR #2381 — not the gpt-5.5-high Max default that drained the $60 API pool.

## Background

PR #2381 added `MODEL="${MODEL:-auto}"` in `.github/workflows/reusable-cursor-run.yml` so an empty
`MODEL` input no longer falls back to cursor-agent's server default (gpt-5.5-high Max Mode).

## Verification

Confirmed: the keepalive cursor lane completed this smoke test using `--model auto` (Cursor's free
Auto bucket), not gpt-5.5-high Max.
