# Keepalive Progress Log — PR #3573

## Scope
Add test coverage for any program functionality with test coverage under 95% or for essential program functionality that does not currently have test coverage.

## Current Status
- ✅ Ran a targeted soft coverage sweep for automation scripts.
  - Command: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m coverage run --source=scripts,.github/scripts -m pytest tests/github_scripts`
  - Coverage report generated via `python -m coverage report -m`.
- 🚧 No new tests have been added yet; coverage remains below the 95% bar for several CI utilities.
- ❌ Acceptance criteria remain unmet because the low-coverage scripts listed below still need dedicated test suites.

## Lowest-Coverage Files (priority order)
1. `scripts/run_multi_demo.py` — 0% (1,271 statements / 0 executed)
2. `scripts/ci_cosmetic_repair.py` — 0% (257 statements / 0 executed)
3. `scripts/verify_codex_bootstrap.py` — 0% (360 statements / 0 executed)
4. `scripts/ci_metrics.py` — 0% (119 statements / 0 executed)
5. `scripts/ci_history.py` — 0% (77 statements / 0 executed)
6. `scripts/sync_test_dependencies.py` — 0% (119 statements / 0 executed)
7. `scripts/sync_tool_versions.py` — 0% (106 statements / 0 executed)
8. `scripts/workflow_smoke_tests.py` — 0% (19 statements / 0 executed)
9. `scripts/verify_trusted_config.py` — 0% (36 statements / 0 executed)
10. `.github/scripts/parse_chatgpt_topics.py` — 98% (1 branch partially covered)
11. `.github/scripts/gate_summary.py` — 99% (remaining branch edge)
12. `.github/scripts/health_summarize.py` — 99% (remaining branch edge)
13. `.github/scripts/decode_raw_input.py` — 99% (2 uncovered branch edges)
14. `.github/scripts/restore_branch_snapshots.py` — 100%

## Next Steps
1. Design focused unit tests for `scripts/workflow_smoke_tests.py` and `scripts/verify_trusted_config.py`, which already have fixtures under `tests/scripts/` but lack coverage instrumentation.
2. Build high-fidelity mocks for the CI automation scripts (`ci_cosmetic_repair`, `ci_metrics`, `ci_history`, `sync_*`) to simulate filesystem interactions and subprocess calls without touching live infrastructure.
3. Break down `run_multi_demo.py` into testable helper functions (or leverage dependency injection) so coverage can reach 95% without executing the full demo pipeline during tests.
4. After each batch of tests, re-run the soft coverage command above, update this progress log, and tick the corresponding checklist items.

_Last updated: 2025-11-16 21:20 UTC._

## 2025-11-16 — Run-Cap Regression (PR #3656)

- **Symptom:** Keepalive posted five instruction rounds within 61 seconds on PR #3656 despite the documented “max two concurrent runs” throttle. Guard summaries showed `cap=2 active=0` even while the orchestrator was still cycling, so the No-Noise policy was violated.
- **Root cause:** `.github/scripts/keepalive_gate.js#countActive` only considered runs whose status was `queued` or `in_progress`. Completed runs were treated as inactive immediately, so the 5-minute cooling window defined in `docs/keepalive/GoalsAndPlumbing.md` Section 3 never engaged.
- **Fix:** Re-introduce the documented five-minute lookback by counting `completed` orchestrator runs whose `updated_at` timestamp is within 300 seconds. These runs populate a new `*_recent` breakdown bucket so operators can see when the cap is held due to recently-finished work.
- **Next validation:** Once merged, replay the PR-meta workflow on a test PR, trigger one keepalive round, and confirm that the next scheduled sweep logs `CAP: ok=false reason=run-cap-reached cap=2 active=2` until five minutes elapse.
