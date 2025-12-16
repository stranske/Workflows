# Keepalive Gap Assessment (2025-02)

> Review the canonical contract in [`GoalsAndPlumbing.md`](GoalsAndPlumbing.md) and [`Observability_Contract.md`](Observability_Contract.md) before implementing changes.

## Findings

1. **Instruction markers now match the contract (with legacy tolerance)**
   - The canonical marker format remains `<!-- codex-keepalive-marker --> <!-- codex-keepalive-round: N --> <!-- codex-keepalive-trace: TRACE -->`.【F:docs/keepalive/Observability_Contract.md†L43-L71】
   - `renderInstruction` now emits the canonical `codex-` prefixed `round` and `trace` markers in addition to the sentinel marker, so posted comments satisfy the documented contract.【F:.github/scripts/keepalive_contract.js†L42-L60】
   - PR-meta detection now accepts both canonical and legacy marker names during the rollout window, so historical comments still register while new instructions use the documented tags.【F:.github/scripts/agents_pr_meta_keepalive.js†L58-L92】

2. **Run-cap checks scope to orchestrator runs by default**
   - The contract defines the dispatch-edge cap as "queued + in_progress orchestrator runs for this PR" only.【F:docs/keepalive/Observability_Contract.md†L63-L73】
   - `countActive` and `evaluateRunCapForPr` now default to orchestrator-only accounting, keeping worker runs out of the quota unless explicitly requested by a caller.【F:.github/scripts/keepalive_gate.js†L476-L860】

## Suggested fixes

- **Align instruction markers with the contract**
  - Update `renderInstruction` to emit the `codex-keepalive-round` and `codex-keepalive-trace` markers, and adjust any regexes that parse instruction headers so the detector and orchestrator agree on the exact tags.
  - Add a short backward-compatibility shim in the detector to accept legacy markers during rollout, but prefer the canonical form in new comments and tests.

- **Enforce the orchestrator-only run cap**
  - Change the run-cap evaluation calls for keepalive dispatch to set `includeWorker: false`, or flip the default so workers are ignored unless explicitly requested.
  - Update the summary line to report orchestrator-only counts, matching the contract’s `cap=<active>/<cap>` definition, and extend tests to prove worker runs no longer consume cap budget.

3. **Repository dispatch payload property limit (RESOLVED 2025-11)**
   - GitHub limits `repository_dispatch` `client_payload` to **10 top-level properties**.
   - Prior implementation sent up to 14 properties, causing `Invalid request. No more than 10 properties are allowed; N were supplied` errors.
   - **Fix:** Nested auxiliary data (`comment_id`, `comment_url`, `round`, `trace`, `idempotency_key`) under a single `meta` object.
   - Affected files: `keepalive_post_work.js`, `agents-pr-meta.yml`, `agents-70-orchestrator.yml`, `agents-keepalive-dispatch-handler.yml`.
   - Handler updated to support both legacy flat payloads and new nested structure for backward compatibility.

4. **Rate limit resilience (RESOLVED 2025-11)**
   - The contract did not specify retry behavior when GitHub API rate limits are hit.
   - Prior implementation failed immediately on rate limit, causing `pr-fetch-failed` without recovery.
   - **Fix:** Added `withRateLimitRetry()` helper with exponential backoff (3 retries, 2s base delay).
   - Applied to PR fetch calls in `keepalive_gate.js` (`evaluateRunCapForPr`, `evaluateKeepaliveGate`).

5. **Checklist progress not preserved across status updates (RESOLVED 2025-12)**
   - The `agents-pr-meta` workflow was regenerating the Automated Status Summary entirely from the source issue on every update.
   - This caused checked checkboxes (recording completed work) to revert to unchecked state.
   - **Root cause:** `buildStatusBlock()` pulled scope/tasks/acceptance directly from source issue without reading existing PR body state.
   - **Fix:** Added `extractBlock()`, `parseCheckboxStates()`, and `mergeCheckboxStates()` helpers.
   - Before generating the status block, the workflow now extracts existing checkbox states from the PR body and merges them into the new content.
   - See Finding #6 for connector bot checkbox capture (implemented 2025-12).
   - Affected file: `agents_pr_meta_update_body.js`.

6. **Connector bot completion signals not captured (RESOLVED 2025-12)**
   - The Codex connector bot (`chatgpt-codex-connector[bot]`) reports task completion by posting **comments** with checked checkboxes (`- [x] Task description`).
   - The `mergeCheckboxStates()` function only preserved checkbox states already present in the **PR body**.
   - **Result:** Agent completed work and reported `[x]` in comments, but the PR body's Automated Status Summary remained unchecked.
   - **Impact:** Keepalive could not detect when acceptance criteria were satisfied, causing infinite dispatch loops.
   - **Fix:** Added `fetchConnectorCheckboxStates()` helper that fetches connector bot comments, parses checked checkboxes, and merges those states into the PR body's Automated Status Summary.
   - Updated `buildStatusBlock()` to accept `connectorStates` parameter and merge connector checkbox states after PR body states.
   - Updated `run()` to call `fetchConnectorCheckboxStates()` before building the status block.
   - **Affected files:** `agents_pr_meta_update_body.js`.
