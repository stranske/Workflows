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
  repository, the run's head-repository identity matches the PR head
  repository, and its current head SHA equals the run head SHA;
- no newer run number or run attempt exists for that SHA;
- the run ID, workflow ID, head SHA, attempt, status, and conclusion remain
  byte-for-byte equivalent to the snapshot whose jobs were evaluated;
- attempt-specific job evidence is available; the publisher never falls back
  to an unbound all-attempt job list;
- the returned changed-file records exactly match the PR's `changed_files`
  count and have no malformed/duplicate records; exactly 3,000 records are
  accepted when the count matches, while a truncated listing fails closed;
  neither the current nor previous path of a rename changes `.github/workflows/`,
  `.github/actions/`, `.github/scripts/`, `.github/path-classification.yml`, or
  `tools/post_ci_summary.py`;
- completed runs contain exactly one completed trusted summary job whose name is
  either `summary` or `gate-summary` (case-sensitive allowlist; duplicate or
  mixed names fail closed). Only an explicit successful run and successful
  summary job can publish `success`; missing, ambiguous, neutral, skipped, or
  incomplete evidence publishes a blocking `error`.

The existing statuses are read before the final run and PR fetch and
latest-attempt check. Any head, base, changed-file count, run-attempt, status,
or conclusion change during that read aborts publication and replay suppression.
The publisher is serialized per head SHA and suppresses an identical replay for
the same run URL. API reads use
bounded retry/backoff with the workflow token only; the final status POST is not
automatically replayed after its last binding check. GitHub does not offer an
atomic compare-and-set status API, so these checks narrow but cannot eliminate
the final read/write race. An abort also leaves an older status untouched.

The workflow has only `actions: read`, `contents: read`, `pull-requests: read`,
and `statuses: write`. It uses no secrets, artifacts, caches, pull-request
checkout, PAT rotation, or App credentials. `Maint 46 Post CI` classifies forks
from `workflow_run.head_repository.id`; missing repository identity fails closed,
and fork recovery is skipped before checkout or status propagation so there is
one writer for fork `Gate / gate` statuses.

## Live protection audit (2026-09-28)

The opener queried active rulesets and legacy branch protection before this
change. Repositories visibly requiring the status were
`Travel-Plan-Permission`, `Pension-Data`, `Inv-Man-Intake`, `Ready`,
`trip-planner`, `Portable-Alpha-Extension-Model` (legacy `gate-summary`), and
`learning-management-system`. Workflows branch protection lists `summary`; the
publisher also accepts a lone `gate-summary` job when that is the Gate rollup
name (for example legacy consumer aliases);
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
