# Workflows Workloop State

## 2026-05-24T02:48:12Z - opener lane materialized issue #2150

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Workflows`.
- Source issue: [#2150](https://github.com/stranske/Workflows/issues/2150) `Coordinate LangSmith fleet observability contract and dashboard ingestion`.
- Branch: `codex/issue-2150-langsmith-fleet-contract` from `origin/main` `a450c067`.
- PR: [#2151](https://github.com/stranske/Workflows/pull/2151) `Issue #2150: Add LangSmith fleet contract`.
- Selection:
  - ACTION A succeeded and the opener-discovery correction from `2026-05-24T02:21:47Z` was applied.
  - Added local guard `/Users/teacher/.codex/automations/pd-workloop-resume/opener-discovery-gate.md` so future `no_op` rounds require a supported-repo open-issue sweep, including unlabeled implementation issues.
  - Required priority discovery still found only Workflows `#2143` credential-expiry alert; normal/low and `repo-review-approved` were empty.
  - Supported-repo open issue sweep found unlabeled LangSmith implementation issues. Repo-specific issues reference `stranske/Workflows#2150` as the parent contract, so the Workflows parent was selected first.
  - Initial cap-health: `total_opener_owned=0`, `raw_cap_reached=false`, `normal_cap_reached=false`, `non_drainable_cap_blocker=false`.
  - Infra repair made no changes; post-repair cap-health remained clear.
- Implementation:
  - Added `docs/contracts/langsmith-fleet-v1.md` defining the shared `langsmith-fleet/v1` NDJSON contract.
  - Added `config/langsmith_fleet_registry.json` mapping active repo-specific LangSmith issues, surfaces, operations, artifact names, rollout status, and required domain fields.
  - Added `scripts/langsmith_fleet.py` to validate records and summarize registry status as missing, invalid, stale, or valid.
  - Added valid/invalid fixtures and tests for shared fields, registry domain fields, safe hash/reference requirements, stale status, and markdown summary output.
  - Updated dashboard and metrics developer docs to point at the new fleet artifact contract and validator.
- Validation:
  - `python -m pytest tests/scripts/test_langsmith_fleet.py tests/scripts/test_aggregate_metrics.py -q` -> 19 passed.
  - `python -m ruff check scripts/langsmith_fleet.py tests/scripts/test_langsmith_fleet.py` -> passed.
  - `python scripts/langsmith_fleet.py tests/fixtures/langsmith_fleet/valid.ndjson --summary --format markdown` -> passed and rendered status counts.
  - `python scripts/langsmith_fleet.py tests/fixtures/langsmith_fleet/invalid.ndjson` -> expected validation failure for unsafe hash/reference and missing domain fields.
  - `git diff --check` -> passed.
- Routing:
  - PR `#2151` is non-draft with labels `agent:codex`, `agents:keepalive`, and `autofix`.
  - Relay emitted: `pr_opened active.source_repo=stranske/Workflows active.source_issue=2150 active.source_pr=2151 active.next_action=wait_for_keepalive`.
  - Post-open cap-health at `2026-05-24T02:48:12Z`: `total_opener_owned=1`, `raw_cap_reached=false`, `non_drainable_cap_blocker=false`; PR `#2151` state `draining` with active Gate evidence.
- Next action: keepalive owns CI/check follow-up for PR `#2151`; opener can select the next eligible repo-specific LangSmith issue on a later round if cap remains below 5.
