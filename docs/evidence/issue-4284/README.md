# Issue #4284 — Gate run 40551187519 job durations

Live-verification gate for the named Workflows Gate run. Durations are
`completedAt - startedAt` from:

```bash
gh run view 40551187519 --repo stranske/Workflows --json jobs,status,conclusion
```

Retain that payload with:

```bash
python -m scripts.gate_run_view_evidence \
  --input run-40551187519.json \
  --output docs/evidence/issue-4284/gate-run-40551187519.json
```

`gate-run-40551187519.json` keeps the CLI status, conclusion, and the
`python ci / python 3.13` and `python ci / python 3.14` job objects, plus the
calculated seconds and job URLs. Both jobs on this run finished within 600
seconds.

Health 85 is workflow id `387854305` (`Health 85 CI Time Budget`).
`health85-daily-observations.json` is the 2026-10-31 through 2026-11-06 log
extract. `docs/reports/ci-budget.json` retains those dates, minute p50 values,
second equivalents, and source run URLs. That series does not qualify: every
measured p50 is above 600 seconds, and 2026-11-05 and 2026-11-06 are
measurement failures.

Completion is reconciled only after both gates have supporting evidence:

```bash
python -m scripts.issue_4284_completion \
  --issue-view docs/evidence/issue-4284/issue-view-4284.json \
  --gate-evidence docs/evidence/issue-4284/gate-run-40551187519.json \
  --budget docs/reports/ci-budget.json \
  --output docs/evidence/issue-4284/completion-reconciliation.json
```

`issue-view-4284.json` is `gh issue view 4284 --repo stranske/Workflows --json
state,body,comments` on 2026-11-06. The issue is `CLOSED` because closer-core
moved the unmet Health 85 gate to #4482. The named Gate jobs pass, and the
seven Health 85 rows on the issue match `docs/reports/ci-budget.json`, but
that series does not qualify. `completion-reconciliation.json` therefore
records `action=leave_incomplete` and does not edit issue state or acceptance
checkboxes.
