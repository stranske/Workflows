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

Dated acceptance window (only runs created at/after the calendar day):

```bash
python scripts/check_gate_python_job_timings.py --limit 5 --max-seconds 600 \
  --created-after 2026-11-15 \
  --json-out docs/evidence/issue-4260/gate-python-job-timings-2026-11-15.json
```

Single Gate run (pre-merge PR-head, any overall conclusion):

```bash
python scripts/check_gate_python_job_timings.py --run-id <GATE_RUN_ID> \
  --max-seconds 600 \
  --json-out docs/evidence/issue-4260/gate-python-job-timings-pr-head.json
```

Reports include both job wall-clock (`seconds`) and the Pytest step wall-clock
(`pytest_step_seconds`) when GitHub job steps are present, so Hosted confirmation
can separate suite time from setup overhead.
If fewer than the requested number of qualifying runs exist, the checker still
writes the JSON report with `passed: false`, the observed `run_count`, and the
`required_run_count`. This replaces any older report at the output path and keeps
an empty or incomplete dated window from being mistaken for passing evidence.

## Baseline (2026-10-26, pre-merge)

`gate-python-job-timings-baseline-2026-10-26.json` records a **FAIL**: three of
five sampled successful Gate PR runs had at least one python job over 600 s
(worst: 3.14 = 727 s on run 40305992256). Coverage is correctly limited to 3.14
on this PR's Gate runs; Hosted wall-clock variance still exceeds the policy.
Do not mark the timing acceptance criterion complete until a fresh checker run
passes on or after 2026-11-15 (and after merge for the Hosted Gate follow-up).

## Latest successful PR window (2026-10-26, post-#4267)

`gate-python-job-timings.json` still records a **FAIL** on the five latest
successful Gate PR runs (single-runtime coverage already on `main` via
`coverage-python-version: '3.14'`; 3.13 correctly runs with coverage off):

| Run | 3.13 job (pytest) | 3.14 job (pytest) | Within 600s |
| --- | ---: | ---: | --- |
| 40366154608 | 525 s (492) | 544 s (504) | yes |
| 40362782097 | 648 s (618) | 715 s (680) | no |
| 40359530080 | 373 s (342) | 704 s (670) | no (3.14) |
| 40359091581 | 526 s (492) | 741 s (698) | no (3.14) |
| 40356027024 | 380 s (353) | 561 s (525) | yes |

Pytest alone often exceeds 600 s on the slower Hosted samples (~50k tests).
Keep the Nov 15 AC unchecked until `--created-after 2026-11-15 --limit 5` passes.

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
duration still exceeds the 10-minute job budget on this sample.

## PR-head sample (2026-10-26, run 40317065551)

`gate-python-job-timings-pr-head-2026-10-26-latest.json` evaluates the later
successful Gate run 40317065551 on the same PR (coverage still limited to 3.14):

| Job | Job seconds | Pytest step seconds | Within 600s |
| --- | ---: | ---: | --- |
| `python ci / python 3.14` (coverage on) | 766 | 718 | no |
| `python ci / python 3.13` (coverage off) | 664 | 633 | no |

Pytest step time alone is already over the 600 s job budget on both legs for
this sample (Hosted log summary lines were 710.66 s / 626.31 s). Hosted
confirmation remains **FAIL** until suite wall-clock drops; re-check after
merge, then again on 2026-11-15 with `--created-after 2026-11-15` and the
five-run window.
