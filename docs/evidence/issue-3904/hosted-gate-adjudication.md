# Adjudication of the hosted Gate pair

The measured numbers are in [hosted-gate-comparison.md](hosted-gate-comparison.md)
and [hosted-gate-comparison.json](hosted-gate-comparison.json). This note records
what those numbers do and do not establish.

## What was compared

Both arms are required Gate runs of `.github/workflows/pr-00-gate.yml` using
`.github/workflows/reusable-10-ci-python.yml` on `ubuntu-latest`.

| | Before | After |
| --- | --- | --- |
| Run | [41985113733](https://github.com/stranske/Workflows/actions/runs/41985113733) | [41992454868](https://github.com/stranske/Workflows/actions/runs/41992454868) |
| Head | `62a8612d29af6aa7b8d778eb14d352de042356bb` | `ccab949a59c9bc03b1a5e7a5cea66bbaee44308c` |
| Tested merge | `51e2aae6d84ef5f25be91cb7cb61ea3c352774ac` | `bcddc346f45cc8bd928b3840252b778b7e1ce2bd` |
| Workflow wall | 07:08:19Z–07:33:11Z (1492s) | 08:10:33Z–08:37:01Z (1588s) |
| Conclusion | success | success |

The tested SHAs have identical `scripts/langchain/pr_verifier.py`,
`requirements.lock`, `pyproject.toml`, `pr-00-gate.yml`, and the reusable
workflow's pytest argv assembly. Each Python version kept four workers, the same
coverage probe, the same CPU model (3.13: AMD EPYC 7763; 3.14: AMD EPYC 9V45),
and the same cache hits (`uv`, pytest, and the CI artifact cache). The reader
reports `configuration_identical` and `timing_controlled` as true. This is one
pair, not a repeated trial.

Run 38938420079 is not this pair. It failed and scheduled Python 3.12 and 3.13.
The required Gate matrix is Python 3.13 and 3.14, with coverage on 3.14.

Local collection of the three scoped files on this checkout:

```sh
python -m pytest --collect-only -q \
  tests/scripts/test_pr_verifier_delivery_destinations.py \
  tests/scripts/test_pr_verifier_prompt_coverage.py \
  tests/scripts/test_pr_verifier_body_overall_integration.py
# 32028 tests collected in 3.68s
```

That matches the hosted per-file sum (27195 + 3750 + 1083). The old-to-retained
mapping for named regressions is `docs/ci/verifier-grammar-matrices.md` and
`docs/ci/verifier-grammar-inventory.json`.

## Coverage

On Python 3.14, `scripts/langchain/pr_verifier.py` kept 3030 executed lines and
1168 executed branches. Lost lines, lost branches, gained lines, and gained
branches are all empty. The whole-suite aggregate moved from 92.49% to 92.48%.
That percentage is not the equivalence result.

`scripts/ci_test_growth.py` is the only other file whose executed line numbers
differ. Its source changed (127 insertions and 3 docstring deletions between the
tested SHAs), so those line numbers are not the same statements. Covered lines
there moved from 29 to 76 and covered branches from 6 to 28. No executable
statement was deleted.

## Timings

Python job walls, not the whole workflow, are the suite measurements. The
workflow wall grew from 1492s to 1588s because the python jobs started later
(about 12 minutes versus about 14 minutes after run creation). That pre-pytest
interval is outside the grammar suite.

| Python | Job wall | Startup | Pytest step | Collection | Max worker | Scoped JUnit worker-seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3.13 before | 674s | 20s | 646s | 46.865s | 631.972s | 801.976 |
| 3.13 after | 604s | 25s | 567s | 46.669s | 555.094s | 529.264 |
| 3.14 before | 463s | 20s | 431s | 28.950s | 394.968s | 461.931 |
| 3.14 after | 412s | 22s | 377s | 29.699s | 343.198s | 299.053 |

Collection and the longest worker overlap under xdist, so those clocks are not
added. In-pytest reporting has no nonnegative remainder on the controller clock.
The record-summary step is under the one-second Actions resolution. Post-pytest
steps are a few seconds (`after_pytest_seconds` in the job payloads).

Scoped JUnit worker-seconds fell by 272.712s on 3.13 and 162.878s on 3.14.
Delivery destinations remain the largest suite: 634.913s to 407.623s on 3.13,
and 362.316s to 228.104s on 3.14.

## Ten-minute aim

The slowest after python job is Python 3.13 at 604s. That is 4s over 600s.
Python 3.14 is under the aim at 412s. The whole Gate workflow is not under 10
minutes. The target is not met. The residual gap inside the python job is those
4s of wall time, and the dominant remaining suite cost is
`tests.scripts.test_pr_verifier_delivery_destinations` (407.623 worker-seconds
on 3.13). The single longest function is now
`tests.workflows.test_agents_guard_publication::test_actual_head_publisher`
(47.360s on 3.13), which this change does not own.

No coverage, security, or merge gate was weakened.
