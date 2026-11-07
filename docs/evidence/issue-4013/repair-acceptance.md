# Issue #4013 closer repair acceptance (#4014 implementation retained)

## Ranking evidence (not invented)

1. **Issue dispatch (primary):** [GitHub issue #4013](https://github.com/stranske/Workflows/issues/4013) lists lane-D targets in Orchestrator order with per-file uncovered mass and escaped-defect/churn signals:
   - `scripts/langchain/verifier_config.py` (3 units)
   - `scripts/reusable_ci_scope.py` (90)
   - `tools/post_ci_summary.py` (243)
2. **Repository ranker artifact (supporting):** `docs/evidence/issue-3743/launch-boundaries/wf-ranking.json` records the ranker method (`last400 script-touching commits; repair-subject proxy…`) and includes `scripts/langchain/verifier_config.py` and `scripts/reusable_ci_scope.py` in the ranked set (churn / `repair_history_proxy` fields). `tools/post_ci_summary.py` is not named in that snapshot; selection for post-CI summary is justified by the issue body’s uncovered-mass ordering (243 units), not by a separate invented proof.

## Gate coverage configuration

From `.github/workflows/pr-00-gate.yml` → reusable `./.github/workflows/reusable-10-ci-python.yml`:

- Full test tree with `-m "not quarantine and not slow"`, `-n auto --dist load`
- `--cov` with repo `pyproject.toml` (`branch = true`, sources `scripts`, `tools`, `src`)
- Coverage enforced on Python **3.14** (`coverage-python-version: '3.14'`, `artifact-prefix: gate-`)

Hosted `gate-coverage.json` artifacts for PR #4014 runs (e.g. run `39009966088`) are no longer downloadable from GitHub Actions retention; local gate-equivalent replay below substitutes.

## Target gap accounting (statements and branches separate)

Command (each SHA):

```bash
bash docs/evidence/issue-4013/run_gate_coverage.sh <sha> docs/evidence/issue-4013/gate-coverage-<label>.json
```

| Phase | SHA | Missing statements | Missing branches | Combined |
| --- | --- | ---: | ---: | ---: |
| Pre-#4014 (main parent) | `399252311611fff8add9d0b34303910654bd8d5a` | 182 | 159 | **341** |
| Merged #4014 head | `f8318e2a02676bd18d9577592250879e914b495c` | 59 | 61 | **120** |
| **Delta** | | **123** | **98** | **221** |

Per-file post merge (`gate-coverage-post-4014.txt`):

- `verifier_config.py`: 0 statements, 1 branch (1 combined)
- `reusable_ci_scope.py`: 13 statements, 12 branches (25 combined)
- `post_ci_summary.py`: 46 statements, 48 branches (94 combined)

**Target:** ~180 combined units from the issue chunk. **Achieved:** 221 combined under gate-equivalent measurement (**no shortfall**). PR #4014’s focused three-module `--cov` figure (182→121) used a narrower run; gate-equivalent whole-suite numbers above are the authoritative gate-style accounting for this repair.

Pre/post full `coverage.json` outputs (~3.2 MB each) are produced by the script above and were kept locally under `docs/evidence/issue-4013/` (not committed due to size); summaries are in `gate-coverage-pre-4014.txt` and `gate-coverage-post-4014.txt`.

## Deliberate break / revert

- Runner: `docs/evidence/issue-4013/run_deliberate_break_proofs.py`
- Evidence: `docs/evidence/issue-4013/deliberate-break-proof.json` — **30** production mutations, **34** pytest node executions (all parameter cases for added tests), every case **RED** under mutation and **GREEN** after restore (`all_red` / `all_green` verified).
- Mapping: each `mutation_id` in the JSON lists affected `node_id`s and exit codes.

## Validation

```bash
/opt/anaconda3/bin/python3 -m pytest -q tests/scripts/test_reusable_ci_scope.py tests/scripts/test_verifier_config.py tests/test_post_ci_summary.py --no-cov
# 141 passed
```

Pytest collection listing for the three modules: `docs/evidence/issue-4013/pytest-collect-three-modules.txt`.
