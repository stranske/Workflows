# PR #4711 regression follow-up — 2026-11-16 UTC

Starting commit: `ec594c0898ee34348159c5b28cb1aad6e59cfb98`.

The progress-review regression omitted `ANTHROPIC_API_KEY`. Adding that key to
the existing in-memory mutation cases reproduced two failures (environment and
script wiring), with ten other Anthropic cases passing. Using the shared
`PROVIDER_KEYS` inventory in the progress-review assertion fixes both cases.

Validation:

```sh
pytest tests/workflows/test_no_api_keys_in_keepalive.py -m 'not slow' -q
# Before changes: 53 passed. After changes: 65 passed, exit 0.
ruff check tests/workflows/test_no_api_keys_in_keepalive.py
# All checks passed.
black --check --line-length 100 tests/workflows/test_no_api_keys_in_keepalive.py
# 1 file would be left unchanged, exit 0.
```

The required repository-wide Black check could not pass in this run. Its default
worker setup raised `PermissionError: Operation not permitted`; a single-worker
retry stalled during source discovery and was interrupted. A verbose retry with
`BLACK_NUM_WORKERS=1 timeout 120s black --check --line-length 100
--exclude '(\.workflows-lib|node_modules)' --verbose .` timed out (exit 124)
during discovery. This does not establish repository-wide formatting success.

The added mutation cases replace the parsed YAML in memory. They do not satisfy
the actual-workflow mutation/restoration acceptance criterion. The protected
Codex workflow was not edited; it still matches the starting commit byte for
byte, SHA-256 `b1c5e9de2a8331cc52d60f0edb3a222ab5b3004a93b8b7c9034deb688e24d7de`.

GitHub reported PR #4711 open, unmerged and ready for review. There is no
delivered merge SHA for this change yet. After delivery, an approved
`agent-high-privilege` run must repeat the named regression, actual-workflow
mutation and exact-byte restoration at that merge SHA, then capture a qualifying
hosted analysis round at the same SHA. This `agent-standard` run cannot mutate
workflow files. No pending acceptance checkbox is completed by these tests.

The GitHub connector rejected adding `needs-human` and posting the blocker
comment: both operations require approval, while this run's approval policy is
`never`. Local staging also failed because `.git` is mounted read-only
(`Unable to create .git/index.lock`). The changes remain uncommitted in the
working tree.
