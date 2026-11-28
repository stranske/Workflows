# Automated Post-CI Status Summary

Start with the required `summary` check on the PR's current head. Gate also
publishes a `Gate / gate` commit status from the same aggregate verdict. A
cancelled run can leave that status stale. See the [Gate check contract](../ci/WORKFLOW_SYSTEM.md#gate-summary-job-pr-00-gateyml-job-summary).

## Read the report

The [Gate workflow](../../.github/workflows/pr-00-gate.yml) uses
[`tools/post_ci_summary.py`](../../tools/post_ci_summary.py) to render the
head SHA, workflow and job results, required contexts, and available coverage.
Gate writes the report to the anchored PR comment and uploads `gate-summary.md`
to the corresponding Actions run. Open the artifact from that run or download
it locally, replacing `RUN_ID` with the run for the head under review.

```bash
gh run download RUN_ID -R stranske/Workflows -n gate-summary.md
```

Check the artifact's head SHA before using its job and coverage links. The
artifact is a snapshot taken while the summary job is running. Use the final
check for its terminal result. Coverage and Docker details can appear pending
when their artifacts are unavailable.

## Recover a missing summary

Follow the [Gate runbook](RUNBOOK.md#gate-stuck-or-red) to locate the failed or
cancelled job and rerun Gate. [Maint 46](../../.github/workflows/maint-46-post-ci.yml)
has a separate recovery path for eligible same-repository PR runs and skips it
when the Gate summary succeeds. The
[Gate Fork Status Publisher](../../.github/workflows/pr-00-gate-fork-status.yml)
handles fork status publication.

Gate's `summary` job is required by the
[required-context configuration](../../.github/config/required-contexts.json).
The Gate detect job and its Docker conditions determine docs-only applicability.
Use the [workflow system guide](../ci/WORKFLOW_SYSTEM.md#gate-pr-00-gateyml) and
the authored workflow when diagnosing a skipped leg.
