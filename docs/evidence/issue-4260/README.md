# Issue #4260 — Gate python job timing policy

Acceptance (read on **2026-11-15**): across the five latest successful Workflows
Gate `pull_request` runs, `python ci / python 3.13` and `python ci / python 3.14`
must each finish in at most 10 minutes (600 s).

## Checker

```bash
python scripts/check_gate_python_job_timings.py --limit 5 --max-seconds 600 \
  --json-out docs/evidence/issue-4260/gate-python-job-timings.json
```

## Baseline (2026-10-26, pre-merge)

`gate-python-job-timings-baseline-2026-10-26.json` records a **FAIL**: three of
five sampled successful Gate PR runs had at least one python job over 600 s
(worst: 3.14 = 727 s on run 40305992256). Coverage is correctly limited to 3.14
on this PR's Gate runs; Hosted wall-clock variance still exceeds the policy.
Do not mark the timing acceptance criterion complete until a fresh checker run
passes on or after 2026-11-15 (and after merge for the Hosted Gate follow-up).
