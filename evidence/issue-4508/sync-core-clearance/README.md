# Issue #4508 sync-core clearance evidence

Pinned consumer `Python CI / typecheck-mypy` log excerpts for the agent-verifiable
half of “next sync-core round classifies trip-planner#1957 without this finding.”

| File | Source | Head | Run / job |
| --- | --- | --- | --- |
| `typecheck-mypy-red.log` | Original shipment-caused failure | `041bd22f043a` | [42325493922](https://github.com/stranske/trip-planner/actions/runs/42325493922) / job `128260180158` |
| `typecheck-mypy-green.log` | Regenerated sync PR after source fix | `948406465cf7` | [42327976097](https://github.com/stranske/trip-planner/actions/runs/42327976097) / job `128267659502` |

Excerpts keep GitHub Actions timestamp prefixes so they match raw job logs that
sync-core classifies. The red excerpt retains the verbatim fingerprint from round
`20261107T014654Z`; the green excerpt retains the mypy success line from the
regenerated head (no `ci_history.py` / `[no-redef]`).

Classifier: `scripts/sync_core_shipment_finding.py` (also covered by
`tests/scripts/test_ci_history.py`). Live sync-core classification remains external.
