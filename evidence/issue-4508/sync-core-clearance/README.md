# Issue #4508 sync-core clearance evidence

Pinned consumer `Python CI / typecheck-mypy` log windows for the agent-verifiable
half of “next sync-core round classifies trip-planner#1957 without this finding.”

| File | Source | Head | Run / job |
| --- | --- | --- | --- |
| `typecheck-mypy-red.log` | Original shipment-caused failure | `041bd22f043a` | [42325493922](https://github.com/stranske/trip-planner/actions/runs/42325493922) / job `128260180158` |
| `typecheck-mypy-green.log` | Regenerated sync PR after source fix | `948406465cf7` | [42327976097](https://github.com/stranske/trip-planner/actions/runs/42327976097) / job `128267659502` |

Windows keep GitHub Actions timestamp prefixes and neighboring ANSI-colored
command lines so they match raw downloaded job logs that sync-core classifies.
The red window retains the verbatim fingerprint from round `20261107T014654Z`;
the green window retains the mypy success line from the regenerated head (no
`ci_history.py` / `[no-redef]` after ANSI normalization).

Classifier: `scripts/sync_core_shipment_finding.py` (also covered by
`tests/scripts/test_ci_history.py`). Live sync-core classification remains external.

```text
python scripts/sync_core_shipment_finding.py evidence/issue-4508/sync-core-clearance/typecheck-mypy-green.log
# cleared → exit 0

gh api repos/stranske/trip-planner/actions/jobs/128267659502/logs | \
  python scripts/sync_core_shipment_finding.py -
# cleared → exit 0 on the live regenerated head
```
