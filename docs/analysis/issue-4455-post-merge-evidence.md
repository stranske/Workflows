# Issue #4455 post-merge evidence

Both acceptance criteria were verified at 2026-11-07T06:18:12Z. Successful
maint-71 runs now appear among the latest three, and #4364 has no sync-core
comment after those runs.

The requested `gh run list --workflow maint-71-merge-sync-prs.yml --repo
stranske/Workflows --limit 3` and `gh issue view 4364 --repo stranske/Workflows
--comments` commands were attempted but could not connect to `api.github.com`.
The connected GitHub API supplied equivalent observations. The
[latest receipt](../../tests/fixtures/issue_4455/latest_runs_evidence.json)
retains the unfiltered API-order prefix through the third maint-71 match,
a separate successful-run read, and projections of every issue comment.
The workflow-specific runs endpoint was unavailable through this connector;
filtering the repository runs response yielded three matches on its first page.
These are observations at collection time, not a continuing workflow-health claim.

- [x] Confirm maint-71 started after #4443 merged into main.
  [PR #4443](https://github.com/stranske/Workflows/pull/4443) merged at
  2026-11-05T02:46:26Z as `81e575a008db219b8b63761014025d182d095128`.
  The latest three maint-71 runs at collection were
  [42346303152](https://github.com/stranske/Workflows/actions/runs/42346303152)
  (2026-11-07T06:16:59Z, in progress),
  [42346256308](https://github.com/stranske/Workflows/actions/runs/42346256308)
  (06:16:18Z, success), and
  [42346191321](https://github.com/stranske/Workflows/actions/runs/42346191321)
  (06:15:28Z, success). All ran on main after the merge. A separate read of
  run 42346256308 confirmed completion at 06:16:53Z with conclusion success.
- [x] Confirm the consumer report excludes the original subscription findings.
  The previously retained
  [merge job log](https://github.com/stranske/Workflows/actions/runs/41958285569/job/127018407721)
  emits the Portable-Alpha-Extension-Model#2454 report at
  2026-11-05T03:00:38Z. It binds head
  `3512f549a602be0cf61b7873f39bf07acf2d6924` to source
  `81e575a008db219b8b63761014025d182d095128`. All six active findings concern
  other paths; none concerns `scripts/langchain/_llm_client.py` or original
  threads `r4434482074` and `r4434491654`. The
  [original receipt](../../tests/fixtures/issue_4455/post_merge_evidence.json)
  preserves that successful run and report. Its consumer blockers are historical
  observations and were not re-evaluated during this follow-up.
- [x] Confirm no sync-core comment on #4364 follows the verified run.
  A fresh API read returned all 39 comments in one page of capacity 100.
  The comment IDs and 13 sync-core handoff markers match the original receipt.
  The latest sync-core comment remains
  [2026-11-04T06:00:32Z](https://github.com/stranske/Workflows/issues/4364#issuecomment-6623829810),
  before both the original and newly verified successful runs.

Acceptance status:

- [x] A success appears among the latest three maint-71 runs after the fix merge.
- [x] No sync-core comment on #4364 is dated after the verified successful run.

Validation: `pytest -q tests/scripts/test_issue_4455_post_merge_evidence.py -m
"not slow"` passed all nine tests; Ruff passed. The original six tests retain
historical evidence, including the earlier failed latest-three check. Three new
tests replay the fresh unfiltered selection, separately confirmed successful run,
and complete comment page. They validate retained observations; future acceptance
checks require fresh API reads.

Repository-wide Black validation passed for all 953 discovered Python files
with line length 100 and the required exclusions. The ordinary CLI stalled
awaiting restricted worker notifications. The successful invocation used one
worker and a 50 ms event-loop heartbeat; formatting rules and discovery were
unchanged.

The checked-out workspace mounts `.git` read-only; staging failed with
`Unable to create .git/index.lock: Read-only file system`. An isolated checkout
under `/tmp/issue-4455-acceptance` is used to prepare the commit and patch.
PR #4519 was read back as open and ready for review (`draft=false`).
The connected GitHub tool rejected the PR checklist update, blocker comment,
and `needs-human` label: those writes require approval, while this run's approval
policy is `never`. Remote checkboxes remain unchanged; the completed checklist
above records verified local progress.

Follow-up observation at 2026-11-07T06:39:33Z verifies the remaining task's
ancestry requirement. The
[comparison](https://github.com/stranske/Workflows/compare/81e575a008db219b8b63761014025d182d095128...ef0e6beafd4acd8f3a9ead3ff43765dba513bbc9)
reports main's run head as 38 commits ahead and zero behind the fix, with
the fix's merge commit itself as merge base. The new
[ancestry receipt](../../tests/fixtures/issue_4455/main_ancestry_evidence.json)
retains that response projection and three post-merge maint-71 starts. A new
test binds both the earlier successful run and these newer starts to that exact
comparison, so a timestamp alone cannot establish that a run contains the fix.
All ten targeted evidence tests and Ruff pass.

The latest-three observation in this follow-up contains one in-progress run
and two cancelled runs; it does not establish a new successful latest-three
observation or supersede the successful observation above. A fresh read of all
39 issue comments still finds no later sync-core handoff. Updating PR #4519's
remaining checkbox was attempted after verification, but the connected tool
again required approval unavailable under this run's `never` policy. Its
remote checkbox therefore remains unchecked.
