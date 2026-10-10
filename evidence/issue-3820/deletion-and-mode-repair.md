# Deletion stability and expanded-mode repair

Originating exact-a4e888b5257eb270485bce86c9c20e3a0f7aaa1d review findings4238228390 and4238228394 were read and adopted. Earlier finding-specific pagination acceptance4238213843 remains historical, not acceptance of this further change.

## Production negative controls

Before the repair, the new deletion-shift test failed: conversation:deletion returned comments.complete=true despite missing boundary record7. The old mode guard yielded5FAIL/1PASS: typo, empty, EVALUATE, trailing whitespace and literal shell syntax were wrongly accepted; checkbox was already rejected. These are executed old-production failures, not hypothetical examples.

After implementing the fix, deliberately disabled the actual source/template full-page stability pass and restored the old permissive unknown-mode branch. `node --test --test-name-pattern='deletion shifts' .github/scripts/__tests__/agents-verifier-context.test.js` failed exit1 on conversation:deletion. `python3 -m pytest tests/workflows/test_verifier_evidence_profile.py -k expanded_checkbox_rejects --no-cov -q` failed exit1,5failed/1passed. Restored both production files byte-identically and reran the named tests GREEN.

Restored SHA256:
- root and template context JS: f498e363c14a71773cc563366938ecc195f2f6e95e1d880a970f235025b4c9fc
- reusable workflow: c0c7b5699aa7c7f3f06e67ef0feff12be83c5ffeabd18f9ff64f55e7d861d06a

## Fixed behavior and executed validation

One bounded re-read of every collected comment page (including terminal link) compares SHA256 of ordered IDs, bodies, author, URL and next-link presence. A deletion shift, body/reference edit, terminal-boundary change, malformed result or failed re-read keeps discovery unavailable and preserves earlier findings. Existing positive identities, monotonic direction and duplicate-before-body-filter checks remain. Each channel has at most10collection pages and10stability pages, no retry loop. Single-page sources are unchanged. This is observed stability, not a transactional API snapshot.

Expanded mode now accepts exact evaluate/compare only before any exports/generation; all other inputs reject. Positive workflow process tests supply actual caller mode, rather than a missing-mode fixture. Standard compatibility remains unchanged.

- Node context suite137PASS, including12unstable-snapshot/channel cases and stable ascending/descending controls. Two focused deletion/stable-order tests PASS after restoration.
- Workflow evidence-profile34PASS after correction; six rejected modes and actual evaluate/compare process paths exercised.
- Focused4013PythonPASS41.78s, with authenticated immutable Workflows3802capture; same command/file list as pagination-and-mode-repair.md plus5newmode cases.
- Ruff, Black(py312), actionlint, template sync/completeness and diff-check PASS.

Source/template/docs/existingmanifestdescription updated together; no new managed file or scope. Hosted checks and current-head reviewer acceptance remain required. Native configured-provider capacity remains UNKNOWN/NONPASS; no provider or whole-campaign acceptance is claimed.
