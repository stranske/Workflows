# Issue #4508 sync-core clearance evidence

Pinned consumer `Python CI / typecheck-mypy` log excerpts for the agent-verifiable
half of “next sync-core round classifies trip-planner#1957 without this finding.”

| File | Source | Head | Run / job |
| --- | --- | --- | --- |
| `typecheck-mypy-red.log` | Original shipment-caused failure | `041bd22f043a` | [42325493922](https://github.com/stranske/trip-planner/actions/runs/42325493922) / job `128260180158` |
| `typecheck-mypy-green.log` | Regenerated sync PR after source fix | `948406465cf7` | [42327976097](https://github.com/stranske/trip-planner/actions/runs/42327976097) / job `128267659502` |

Lines are stripped of GitHub Actions log prefixes. The red excerpt keeps the verbatim
fingerprint sync-core round `20261107T014654Z` quoted; the green excerpt keeps the
mypy success line from the regenerated head (no `ci_history.py` / `[no-redef]`).

Live sync-core classification remains external; these fixtures drive the local classifier
in `tests/scripts/test_ci_history.py`.
