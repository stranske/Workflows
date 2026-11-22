# Cosmetic Test Repair Workflow

The cosmetic repair workflow provides a **manual**, dispatch-only escape hatch
for acknowledged formatting and tolerance drift. It never runs automatically on
push or pull requests. Instead, a repository maintainer can trigger the
workflow when a cosmetic failure blocks a merge.

## When to use the workflow

* Pytest failures whose test calls `record_property("markers", "cosmetic")`
  and carries a `COSMETIC_*` payload in the assertion message. The JUnit
  classifier reads that property. A pytest selection marker alone does not
  populate it.
* Known guard rails exist in the affected files (for example, lines annotated
  with `# cosmetic-repair: float EXPECTED_ALPHA`).
* The failure can be resolved mechanically by updating stored baselines or
  numeric tolerances.

Do **not** run the workflow for runtime or behavioural regressions—open a
standard fix PR instead.

## Workflow outline

1. Launch the workflow from the **Actions** tab by selecting
   _Maint 45 Cosmetic Repair_ → **Run workflow**. Select the base for the test
   checkout and repair PR. Optional inputs select the supported Python runtime,
   dry-run mode, or a suffix for the repair branch.
2. The job installs the selected base's locked dependencies in one virtual
   environment and runs pytest once. It retains `pytest-report.xml` and the
   original exit code.
3. The repair helper parses that same report with `--require-all`. Every
   originally failed case must supply a `COSMETIC_TOLERANCE` or
   `COSMETIC_SNAPSHOT` instruction. Both modes check the corresponding
   `# cosmetic-repair:` guard.
4. A preview lists the validated instructions without editing files. Apply
   mode edits the guarded targets and keeps their guard comments.
5. One writer opens a pull request against the selected base from
   `cosmetic-repair/<run-id>` (plus any suffix), staging only those exact
   changed files. The PR is labelled `testing` and `autofix:applied`.
6. The job summary reports the original exit code, repair outcome, and any
   confirmed PR URL. The `cosmetic-repair-artifacts` upload contains the original
   report and, when generated, `.cosmetic-repair-summary.json`. Review and test
   the proposed change in its PR; Maint 45 does not rerun pytest after editing.

If re-run after the drift is already repaired, the script exits cleanly without
creating a new branch or PR.
Missing or invalid reports, ordinary failures, and a failed report that cannot
produce a repair remain failed and open no PR.

## Local execution

Developers can run the same logic locally:

```bash
python -m pytest -o junit_family=xunit1 --junitxml=pytest-report.xml
python -m scripts.ci_cosmetic_repair --apply --skip-pr --require-all --report pytest-report.xml
```

* Use `--dry-run` to inspect the planned fixes without modifying files.
* Pass `--report <path>` to analyse an existing JUnit XML report instead of
  running pytest.
* `--branch-suffix` lets you append a human-friendly token to the generated
  branch name when creating a PR.

Ensure the working tree is clean before running in `--apply` mode.
`--require-all` also confines targets to the checkout and checks the
guards during preview.
