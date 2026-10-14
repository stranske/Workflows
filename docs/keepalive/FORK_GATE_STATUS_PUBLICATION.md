# Trusted Fork Required Status Publication

Fork pull requests run required workflows with a read-only token. `Gate` and Health 45 Agents Guard therefore cannot publish their required PR-head statuses directly. Their default-branch `workflow_run` publishers publish those statuses without executing or checking out pull-request code.

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

## Health 45 Agents Guard bridge

`agents-guard-fork-status.yml` is centrally managed (not `create_only`) so existing consumers receive the required `Health 45 Agents Guard / guard` context. It subscribes only to `Health 45 Agents Guard` runs and uses immutable default-branch code. It re-fetches and binds the workflow identity/path, open fork PR, default base, exact head, latest attempt, and exactly one completed `guard` job before publishing. Same-repository PRs retain the normal publisher; base-bound `pull_request_target` label events never satisfy the PR-head result. Missing, duplicate, cancelled, incomplete, stale, or untrusted evidence fails closed. The publisher uses only the workflow token, no PR checkout, artifacts, caches, pooled credentials, or automatic write retry; its `agents-guard-fork-status/v1` receipt records guard/publisher attempts and the returned status ID.

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


Health 45 direct label-event publishing and canonical completed `pull_request` guard publishers share a non-cancelling, head-SHA concurrency group. Before joining that group, a read-only classifier re-fetches the triggering run and workflow by numeric ID and requires strict JavaScript equality for the canonical workflow path and name, event, completed status, repository identity, and positive matching workflow IDs. This safely accepts either canonical or `workflow_path@ref` run-path form while refusing case variants, lookalike paths, missing IDs, and unavailable API evidence. Noncanonical or unclassifiable runs skip the publish job, so they cannot replace a pending direct label-event corrective under GitHub's one-pending scheduler. The publisher reconciles current policy receipts before trusting an old guard result; each direct label-event writer also rechecks current policy labels before publication.

Before the direct Health 45 publisher writes, it reads the current PR policy labels (`agent:*`, `agents:auto-pilot`, `agents:keepalive`, and `agents:allow-change`) and requires an exact match with the event snapshot. Unrelated sync and seal metadata labels do not affect that comparison. A label change writes a blocking failure so a stale eligible evaluation cannot retain a green required context. An ineligible label event likewise replaces an existing same-head success with a blocking failure, while preserving an existing non-success verdict or an absent context. A fresh trusted direct eligible evaluation is the only path that recovers success after a direct corrective failure.

A successful Health 45 status starts with `[guard-pr:N] ` for the resolved pull-request number and carries a fixed `guard-policy-sha256` suffix: the SHA-256 digest of the sorted policy-relevant labels. Both trusted writers produce the same receipt. A legacy, missing, or different PR binding cannot preserve success; it requires a fresh trusted direct evaluation. An ineligible direct event may preserve a success only when its current policy-label digest matches that receipt; a missing, malformed, or changed receipt is replaced with a blocking failure. A fork no-op may establish an absent context only while the current policy remains ineligible; if a routing label was added while that old no-op ran, it writes a blocking failure and requires a fresh evaluation. A current-policy-bound success or corrective failure targeted to a canonical direct `pull_request_target` guard run outranks an older fork result for the same exact-head context, including control-path errors and ordinary evaluated results. A direct-status lookup outage preserves an existing failure or error as blocking; it never permits an old fork success to clear that context. An arbitrary historical fork failure remains recoverable by a valid evaluated fork result. This keeps ordinary sync metadata labels from invalidating a current verdict while preventing a revoked or newly eligible routing policy from retaining green.

The receipt canonicalizes routing labels by trim-plus-lowercase, and canonicalizes `agents:allow-change` by lowercase only, matching the guard evaluator: surrounding whitespace never grants protected-file permission. Missing or malformed current-label evidence fails the publishing step before any green status can be written.
