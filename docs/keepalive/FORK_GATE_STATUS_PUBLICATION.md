# Trusted Fork Gate Status Publication

Fork pull requests run `Gate` with a read-only token. The Gate run therefore cannot
write the required `Gate / gate` commit status itself. The
`Gate Fork Status Publisher` is a default-branch `workflow_run` subscriber that
publishes that status without executing or checking out pull-request code.

## Trust and exact-head contract

The publisher re-fetches the workflow run and pull request through the API and
fails closed unless all of these bindings hold:

- the run belongs to this repository, is named `Gate`, uses
  `.github/workflows/pr-00-gate.yml`, and was triggered by `pull_request`;
- the open pull request targets this repository, originates in a different
  repository, and its current head SHA equals the run head SHA;
- no newer run number or run attempt exists for that SHA;
- the pull request does not change `.github/workflows/`, `.github/actions/`,
  `.github/scripts/`, `.github/path-classification.yml`, or
  `tools/post_ci_summary.py`;
- completed runs contain exactly one completed `summary` job. Only an explicit
  successful run and successful summary can publish `success`; missing,
  ambiguous, neutral, skipped, or incomplete evidence publishes a blocking
  `error`.

The run and PR are fetched again immediately before the status write, preventing
a force-pushed head from inheriting a stale success. The publisher is serialized
per head SHA and suppresses an identical replay for the same run URL. GitHub does
not offer an atomic compare-and-set status API, so a final API recheck plus
latest-attempt comparison is the enforcement boundary.

The workflow has only `actions: read`, `contents: read`, `pull-requests: read`,
and `statuses: write`. It uses no secrets, artifacts, caches, or pull-request
checkout. `Maint 46 Post CI` explicitly skips fork PR recovery so there is one
writer for fork `Gate / gate` statuses.

## Live protection audit (2026-09-28)

The opener queried active rulesets and legacy branch protection before this
change. Repositories visibly requiring the status were
`Travel-Plan-Permission`, `Pension-Data`, `Inv-Man-Intake`, `Ready`,
`trip-planner`, `Portable-Alpha-Extension-Model` (legacy `gate-summary`), and
`learning-management-system`. Workflows currently requires `summary` instead;
Trend Model Project and Collab Admin expose disabled rulesets. The remaining
registered consumers returned no visible required status contexts. This is a
point-in-time API audit, not an assertion that hidden or future protection rules
cannot change.

## Validation and rollout

Local contract:

```bash
python3 -m pytest tests/workflows -k 'fork and gate and status' -q
```

The stale-head negative case must report
`PR head no longer matches Gate head`. For a live positive rehearsal, open a
fork PR that changes an ordinary source file, verify the publisher targets the
exact PR head, and capture the publisher run plus `Gate / gate=success` status
URL in the rollout issue. For a live negative rehearsal, force-push after a Gate
run or change a protected control path; capture the blocking error status and
prove no stale success was written.

Roll out `create_only`, one repository at a time, in this order:

1. `Template`, `Travel-Plan-Permission`, `trip-planner`, `Pension-Data`;
2. `Inv-Man-Intake`, `Ready`, `learning-management-system`,
   `Portable-Alpha-Extension-Model`;
3. `Trend_Model_Project`, `Counter_Risk`, `Fine-Art-Archive`, `Orchestrator`;
4. `Doc-Lineage`, `Deliverable-Render`, `Manager-Mosaic`, `Collab-Admin`.

`Manager-Database` remains excluded with its custom Gate workflow. At each phase,
record the current required contexts, one exact-head positive rehearsal, and one
stale-head/control-surface negative rehearsal before continuing. Roll back by
disabling or removing `pr-00-gate-fork-status.yml`; do not weaken branch
protection. Existing Gate behavior remains the fallback while the publisher is
`create_only`.
