## Summary
Monthly docs-drift audit. Doc-rot is this system's most pervasive defect class (the 2026-06 audit found stale counts/claims across the canonical docs). Diff the canonical docs below against the **current tree** and open focused fix PR(s) for any claim that no longer matches reality.

## Scope — canonical docs to verify (this round)
For each, check that every concrete claim (file paths, counts, workflow names, command names, described behavior) matches the current repo:
- [ ] `README.md` — pipeline overview, consumer list, entry points
- [ ] `docs/ci/WORKFLOWS.md` + `docs/ci/WORKFLOW_SYSTEM.md` — workflow inventory (names, triggers, counts)
- [ ] `docs/STRUCTURE.md` — directory/file counts and key-directory prose
- [ ] `docs/INTEGRATION_GUIDE.md` — inputs/secrets/versioning claims vs the reusables
- [ ] `docs/keepalive/GoalsAndPlumbing.md` + `docs/keepalive/Agents.md` — labels, guardrails, agent routing
- [ ] `docs/AGENTS_POLICY.md` + `docs/LABELS.md` — protected-workflow list + canonical label inventory

## How to verify (no hand-waving)
- Cross-check each claim against the actual file/command/workflow it describes; cite the source `path:line` in the fix PR.
- Where a doc-validation test exists it must stay green: `pytest tests/workflows/ -q` (e.g. `test_workflow_naming.py::test_inventory_docs_list_all_workflows` enforces that the inventory docs list every workflow).

## Tasks
- [ ] For each drifted claim found, open a focused fix PR correcting the doc to match reality (link the source `path:line`).
- [ ] Keep PRs small and per-doc where practical; don't rewrite docs wholesale.
- [ ] If a doc is already accurate, tick its box with a one-line "verified vs `<evidence>`" note.

## Non-Goals
- No scaffolding, no TODO-only edits, no net-new docs.
- Don't restructure/rewrite prose that is accurate — fix only drifted claims.
- Not a consumer-template sync (that's `maint-68`); fix the source docs here.

## Done
All scope boxes ticked (verified or fixed); `tests/workflows/` green; doc claims match the tree.

---
_Seeded monthly by `maint-48-docs-drift-audit.yml`. Dedup: one open `[Docs Drift Audit]` issue at a time._
