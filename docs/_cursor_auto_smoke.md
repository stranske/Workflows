# Cursor Auto-Model Smoke Test

Throwaway PR verifying that the keepalive **cursor** lane now runs `--model auto` (Cursor's free
Auto bucket) after PR #2381 — not the gpt-5.5-high Max default that drained the $60 API pool.

Confirmed: the keepalive cursor lane completed this smoke test using `--model auto` (Cursor's free Auto bucket), not gpt-5.5-high Max.
