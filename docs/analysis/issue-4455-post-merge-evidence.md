# Issue #4455 post-merge evidence

Evidence collection completed 2026-11-07T05:55:11Z. The subscription findings
cleared in a successful run on the merged fix. One acceptance criterion remains
open: all three most recent maint-71 runs returned by the API concluded failure.

The requested `gh run list --workflow maint-71-merge-sync-prs.yml --repo
stranske/Workflows --limit 3` and `gh issue view 4364 --repo stranske/Workflows
--comments` commands were attempted, but both failed to connect to
`api.github.com`. The connected GitHub API supplied the evidence instead.
The [retained receipt](../../tests/fixtures/issue_4455/post_merge_evidence.json)
records endpoints and field projections. Recent runs were selected from the
first 100 repository runs, retaining API order and filtering the exact workflow
path; the first three matching rows are recorded below. These are observations
at collection time, not a continuing claim about current workflow health.

- [x] Confirm maint-71 started after #4443 merged into main.
  [PR #4443](https://github.com/stranske/Workflows/pull/4443) merged at
  2026-11-05T02:46:26Z as `81e575a008db219b8b63761014025d182d095128`.
  [Run 41958285569](https://github.com/stranske/Workflows/actions/runs/41958285569)
  started at 2026-11-05T02:55:16Z on that exact commit, concluded success, and
  was last updated at 03:00:45Z. The three recent runs also started after the merge.
- [x] Confirm the consumer report excludes the original subscription findings.
  The [merge job log](https://github.com/stranske/Workflows/actions/runs/41958285569/job/127018407721)
  emits the final Portable-Alpha-Extension-Model#2454 report at 03:00:38Z.
  It binds head `3512f549a602be0cf61b7873f39bf07acf2d6924` to source
  `81e575a008db219b8b63761014025d182d095128`. All six active findings concern
  other paths; none concerns `scripts/langchain/_llm_client.py` or original
  threads `r4434482074` and `r4434491654`. The consumer remains blocked by
  those six other findings and requires a base refresh.
- [x] Confirm no sync-core comment on #4364 follows the verified run.
  The API returned all 39 comments in one page of capacity 100. Thirteen have
  the sync-core handoff marker. The latest is
  [2026-11-04T06:00:32Z](https://github.com/stranske/Workflows/issues/4364#issuecomment-6623829810),
  before the run; the latest Portable-Alpha-specific handoff is
  [2026-11-04T06:00:22Z](https://github.com/stranske/Workflows/issues/4364#issuecomment-6623827321).

Acceptance status:

- [ ] A success appears among the latest three maint-71 runs after the fix merge.
  The returned runs were
  [42344355901](https://github.com/stranske/Workflows/actions/runs/42344355901)
  (2026-11-07T05:49:47Z),
  [42344354188](https://github.com/stranske/Workflows/actions/runs/42344354188)
  (05:49:46Z), and
  [42344311965](https://github.com/stranske/Workflows/actions/runs/42344311965)
  (05:49:06Z). All concluded failure. The historical success establishes the
  fix's post-merge behavior but cannot satisfy this literal latest-three check.
- [x] No sync-core comment on #4364 is dated after the verified successful run.

Validation: `pytest -q tests/scripts/test_issue_4455_post_merge_evidence.py -m
"not slow"` passed all six tests. They replay merge/run ordering, exact source
and consumer-head bindings, findings, comment timestamps, and the distinction
between historical success and the latest-three acceptance criterion. The tests
validate the retained observation; fresh acceptance requires another live read.
Ruff passed. Repository-wide Black validation passed for all 953 discovered
files with the required line length and exclusions. The ordinary CLI first
failed because Python 3.14's multiprocessing startup tried to bind a forbidden
socket. The successful invocation used one worker and kept Black's event loop
polling every 50 ms to accommodate restricted worker notifications; formatter
rules and file discovery were unchanged.

Handoff constraints: this workspace mounts `.git` read-only, so committing to
the checked-out branch is blocked. A commit and apply-ready patch are prepared
in an isolated checkout under `/tmp/issue-4455-review`. Connected GitHub tools rejected the PR-body
update, `needs-human` label, and blocker comment because those writes require
approval and this run's approval policy is `never`. The checklist above records
verified local progress. PR #4519 was independently read back as open and ready
for review (`draft=false`).
