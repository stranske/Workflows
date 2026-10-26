# Issue #4260 — Gate python job timing policy

Acceptance (read on **2026-11-15**): across the five latest successful Workflows
Gate `pull_request` runs, `python ci / python 3.13` and `python ci / python 3.14`
must each finish in at most 10 minutes (600 s).

## Checker

Latest successful PR window (post-merge / Nov 15 acceptance read):

```bash
python scripts/check_gate_python_job_timings.py --limit 5 --max-seconds 600 \
  --json-out docs/evidence/issue-4260/gate-python-job-timings.json
```

Single Gate run (pre-merge PR-head, any overall conclusion):

```bash
python scripts/check_gate_python_job_timings.py --run-id <GATE_RUN_ID> \
  --max-seconds 600 \
  --json-out docs/evidence/issue-4260/gate-python-job-timings-pr-head.json
```

## Baseline (2026-10-26, pre-merge)

`gate-python-job-timings-baseline-2026-10-26.json` records a **FAIL**: three of
five sampled successful Gate PR runs had at least one python job over 600 s
(worst: 3.14 = 727 s on run 40305992256). Coverage is correctly limited to 3.14
on this PR's Gate runs; Hosted wall-clock variance still exceeds the policy.
Do not mark the timing acceptance criterion complete until a fresh checker run
passes on or after 2026-11-15 (and after merge for the Hosted Gate follow-up).

## PR-head sample (2026-10-26, run 40308833794)

`gate-python-job-timings-pr-head-2026-10-26.json` evaluates Gate run
40308833794 on PR #4272 via `--run-id` (overall Gate failed on unrelated
lint-ruff; python jobs themselves succeeded). Observed wall-clock:

| Job | Seconds | Within 600s |
| --- | ---: | --- |
| `python ci / python 3.14` (coverage on) | 560 | yes |
| `python ci / python 3.13` (coverage off) | 673 | no |

Pytest alone was 510.55 s on 3.14 (with coverage) vs 630.30 s on 3.13
(without coverage). Single-runtime coverage is working; 3.13 Hosted pytest
duration still exceeds the 10-minute job budget on this sample. Re-check after
merge, then again on 2026-11-15 with the five-run window.
