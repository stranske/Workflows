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
seconds. The separate Health 85 trailing-seven-day Gate p50 series is not this
file.
