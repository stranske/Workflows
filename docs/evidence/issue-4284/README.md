# Issue #4284 — Gate run 40551187519 job durations

Live-verification gate for the named Workflows Gate run. Durations are
`completedAt - startedAt` from:

```bash
gh run view 40551187519 --repo stranske/Workflows --json jobs,status,conclusion
```

Retain that payload with:

```bash
evidence_dir=docs/evidence/issue-4284
python -m scripts.gate_run_view_evidence \
  --input run-40551187519.json \
  --output "$evidence_dir/gate-run-40551187519.json"
```

`gate-run-40551187519.json` keeps the CLI status, conclusion, and the
`python ci / python 3.13` and `python ci / python 3.14` job objects, plus the
calculated seconds and job URLs. Both jobs on this run finished within 600
seconds.

Health 85 is workflow id `387854305` (`Health 85 CI Time Budget`).
`health85-daily-observations.json` and `docs/reports/ci-budget.json` retain
the seven qualifying UTC dates from 2026-11-12 through 2026-11-18, the p50 in
minutes and seconds, and the original run and artifact URLs. The first four
dates were recovered from daily artifacts. The last three also match the
published report on `ci-time-budget` at the commit recorded in the evidence.
On 2026-11-18, the Workflows measurement used 206 Gate samples. The overall
run failed after the Orchestrator measurement returned HTTP 502.

Completion is reconciled only after both gates have supporting evidence:

```bash
evidence_dir=docs/evidence/issue-4284
python -m scripts.issue_4284_completion \
  --issue-view "$evidence_dir/issue-view-4284.json" \
  --gate-evidence "$evidence_dir/gate-run-40551187519.json" \
  --budget docs/reports/ci-budget.json \
  --output "$evidence_dir/completion-reconciliation.json"
```

`issue-view-4284.json` is `gh issue view 4284 --repo stranske/Workflows --json
state,body,comments` on 2026-11-19. Closer-core had closed #4284 after moving
the unmet Health 85 gate to #4482. The named Gate jobs passed, and all seven
qualifying rows match the [delivery evidence on #4284](https://github.com/stranske/Workflows/issues/4284#issuecomment-7002527234).
`completion-reconciliation.json` records `action=mark_complete` and
`completion_reconciled=true`.
