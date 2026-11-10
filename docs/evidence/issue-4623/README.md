# Issue #4623 live acceptance observation

Observed through **2026-11-10 14:34:09 UTC**. This is a bounded historical
observation, not a claim about future runs or a new source repair.

The requested `gh` commands were attempted, but each failed to connect to
`api.github.com` in the runner. The GitHub connector supplied the equivalent
live API evidence retained in `observation.json`. The replay validator performs
no GitHub writes and does not replace the live observation with mocked results.

- [x] Open the first Maint 71 run after consumer regeneration:
  [42445636759](https://github.com/stranske/Workflows/actions/runs/42445636759),
  started November 8 at 04:09:17 UTC. The unfiltered repository inventory from
  regeneration through that start contains 16 runs and only this Maint 71 run.
- [x] Inspect [consumer PR #2454](https://github.com/stranske/Portable-Alpha-Extension-Model/pull/2454):
  its 3 issue comments, 19 inline comments, and 12 review submissions contain no
  post-delivery repost of the handoff findings. The original November 1 findings
  remain historical; source-fix dispositions on November 8 are owner evidence,
  not acceptance attributed to the original reviewer.
- [x] Inspect all 60 comments on [source issue #4366](https://github.com/stranske/Workflows/issues/4366):
  the last sync-core comment is [6701221366](https://github.com/stranske/Workflows/issues/4366#issuecomment-6701221366)
  at November 7, 02:46:52 UTC. No sync-core comment was created or updated after
  the delivery run. Other actors updated the issue on November 10; a later
  `updatedAt` alone does not mean sync-core resumed bumping it.
- [x] A post-delivery Maint 71 run reports PR #2454 without the old findings:
  the [first run's job](https://github.com/stranske/Workflows/actions/runs/42445636759/job/128623866686)
  binds its report to consumer head `9c85282d05359ddc468d0881ec6b09269ac592a2`
  and source `c2ac6f38d6f2ce73f000158fa6f729bfece82092`, with
  `review_state: clear`, zero active findings, and no finding errors.
  The latest observed run is [42789507724](https://github.com/stranske/Workflows/actions/runs/42789507724),
  November 10 at 09:17:48 UTC; the latest three are retained.
- [x] No sync-core comments follow the delivery run in issue #4366.

[Source PR #4463](https://github.com/stranske/Workflows/pull/4463) merged November 6
at 12:44:41 UTC as `7ab99d09429a3b35aa55f7744f8c75b467f42536`.
The consumer's generated commit records the source revision above and was
created November 8 at 04:08:45 UTC. The source comparison has that repair merge
as its merge base and `behind_by: 0`. PR #2454 merged at 04:40:31 UTC.
The appendix's statement that the fix is not on main is therefore stale.

The first run sealed the consumer head and requested its Gate rerun; it reported
`delivery_sealed_checks_pending`. Its success and clear finding report do not
assert that every delivery check had already passed at 04:09.

Validation:

```sh
node docs/evidence/issue-4623/verify-observation.js docs/evidence/issue-4623/observation.json
node --test tests/scripts/test_issue_4623_live_observation.js tests/workflows/auto_pilot_verify_handoff.test.js
python -m pytest -q tests/workflows/test_auto_pilot_verify_handoff.py -m 'not slow'
```

All pass (20 replay tests and 66 Python handoff regression tests).
`node --test .github/scripts/__tests__/maint71_finding_verification.test.js` also
passes. The replay tests refuse missing comments, a truncated or filtered
inventory, stale head/source bindings, active findings, lookup errors, and
post-delivery sync-core bumps or reposted original findings. The prose review of
the retained discussion supplies the semantic check; the replay only recognizes
the known original wording and reassessment requests.

## Handoff blocker

The four prepared files could not be committed in this run: local `.git` is
read-only, so `git add` cannot create `index.lock`. The GitHub connector rejected
`create_tree` because it requires approval and the run's approval policy is
`never`. The required blocker-comment and `needs-human` label attempts were
rejected for the same reason. The remote PR checklist was not changed.
A run with authorized write access must commit these files to the existing
`codex/issue-4623` branch. PR #4626 was verified open with `isDraft=false`; no
branch, commit, or pull request was created by this run.
