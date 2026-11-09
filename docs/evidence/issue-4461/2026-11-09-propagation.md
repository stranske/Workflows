# Issue 4461 downstream propagation record — 2026-11-09

Follow-up to #4370 (source fix merged by #4448 as
`7b92760527da7c9a7a5282005009b75f7d01cd2e` at 2026-11-05T12:51:50Z). This record
checks that the fix reached stranske/Travel-Plan-Permission#1716 through
generation, and that the finding stopped after the fix. Nothing on the consumer
branch was edited, and no review thread was changed. Every value below was read
from live GitHub state on 2026-11-09.

## Outcome

| Check | Result |
| --- | --- |
| A completed maint-68 regeneration contains the merged source fix | Yes: run `42433992005`, which created consumer head `08c150469cfa` |
| The regenerated consumer file contains the fix | Yes: the fix line is present, and the file matches the #4448 template except for one unrelated `# noqa: ARG002` line |
| maint-71 reports TPP#1716 without this finding | Yes: run `42447027509` reports `findings: []` and `active_review_thread_count: 0` at `08c150469cfa`, then merges it |
| Original thread `discussion_r4434491951` | Superseded: GitHub marks it `isOutdated=true` against the regenerated head, and the PR merged |
| sync-core renewed the #4370 finding after the fix | No: the last bump was for pre-fix head `82c9762a4e61`. On 2026-11-06, sync-core observed fixed head `3b51e44083d4` and did not bump #4370 |

## 1. maint-68 regeneration containing the fix

```console
gh run list --repo stranske/Workflows --workflow maint-68-sync-consumer-repos.yml
gh run view 42433992005 --repo stranske/Workflows --log
```

- Run `42433992005`: `workflow_dispatch`, `completed/success`, created
  2026-11-08T01:22:40Z, source `c2ac6f38d6f2ce73f000158fa6f729bfece82092`.
  The job `Sync stranske/Travel-Plan-Permission` succeeded.
- `git merge-base --is-ancestor 7b92760527da c2ac6f38d6f2` succeeds, so this
  regeneration contains the #4448 fix.
- Log lines from the Travel-Plan-Permission job:

  ```text
  2026-11-08T01:24:22.9461794Z   PLAN_ID: sha256:4017589cec3ca50a3f528f382fe788b40f49cfcd2641214da354672b71ff27da
  2026-11-08T01:24:36.4911593Z   SYNC_BRANCH: sync/workflows-candidate
  2026-11-08T01:24:38.5316934Z M	scripts/langchain/pr_verifier.py
  2026-11-08T01:24:51.0621524Z Created verified sync commit 08c150469cfa35afc9461ba668b8493fdc7a0405 using github-app-installation
  ```

- TPP#1716 has a single commit, `08c150469c` (2026-11-08T01:24:50Z,
  `Template hash: 4017589cec3c`), which is the head that merged.

### Consumer file content at the regenerated head

`scripts/langchain/pr_verifier.py` fetched from Travel-Plan-Permission at each
ref:

| Ref | Contains `payload = _load_object(_slot_path(), label="slot config")` |
| --- | --- |
| `58e7e3bdfe8b` (head named in #4370) | no |
| `82c9762a4e61` (last head bumped on #4370) | no |
| `3b51e44083d4` (2026-11-06 regeneration) | yes |
| `08c150469cfa` (merged head) | yes (line 8778) |

`diff` of the #4448 template copy
(`templates/consumer-repo/scripts/langchain/pr_verifier.py` at `7b92760527da`)
against the consumer file at `08c150469cfa` shows one changed line,
`def invoke(...)`, which gained `# noqa: ARG002` from a later source commit. It
is unrelated to the backup lookup.

## 2. maint-71 report for the regenerated head

```console
gh run view 42447027509 --repo stranske/Workflows --log
```

Run `42447027509` (created 2026-11-08T04:29:38Z) sealed and merged TPP#1716 at
the regenerated head. Excerpt from its summary row:

```json
"repo": "Travel-Plan-Permission",
"pr": 1716,
"head_sha": "08c150469cfa35afc9461ba668b8493fdc7a0405",
"source_commit": "c2ac6f38d6f2ce73f000158fa6f729bfece82092",
"delivery_disposition": "current",
"review_finding_disposition": {
  "schema": "sync-finding-evaluation/v1",
  "raw_active_count": 0,
  "blocked": false,
  "findings": [],
  ...
"active_review_thread_count": 0
```

Merge lines for TPP#1716:

```text
Runtime AC merge guard passed for PR #1716.
✓ Merged successfully (method=merge)
```

GitHub records the merge as `mergedAt=2026-11-08T04:31:40Z`, merge commit
`71d6359516d9`. The run's overall conclusion is `failure`. That failure is a
different PR: `stranske/Portable-Alpha-Extension-Model#2454` returned 405
`All comments must be resolved` (#4366 finding). It did not involve TPP#1716.
The next run, `42447689865` (success, 2026-11-08T04:39:27Z), logs
`✓ Recovered already-merged campaign row from PR #1716 (08c150469cfa35afc9461ba668b8493fdc7a0405)`.

The earliest run that observed the new head was `42434199041`
(2026-11-08T01:25:32Z). It logged
`seal: stranske/Travel-Plan-Permission#1716 sealed` for `08c150469cfa`.

## 3. Original review thread disposition

```console
gh api repos/stranske/Travel-Plan-Permission/pulls/comments/4434491951
```

- Author `Copilot`, created 2026-11-01T05:10:54Z, path
  `scripts/langchain/pr_verifier.py`, `original_commit_id e7d6a5dffae6`,
  current `line: null`.
- GraphQL `reviewThreads` for PR 1716: `isOutdated=true`, `isResolved=false`,
  and no reply.
- **Disposition: superseded.** The fix was generated into the file the thread
  comments on (§1), and GitHub marks the thread outdated against the
  regenerated head. maint-71 counted 0 active threads at `08c150469cfa`, and
  the PR is merged. This run did not resolve the thread through the API,
  because the issue asks for its disposition to be recorded, not for the PR to
  be edited. Resolving a thread on a merged PR would not change any gate.

## 4. sync-core comments on #4370

`gh api repos/stranske/Workflows/issues/4370/comments` shows that every
`sync-core/v1 handoff fp=08f20d972654` bump came before the fix:

| Comment time | Head reported "Still present" |
| --- | --- |
| 2026-11-02T17:15:03Z | `e1d8a8ed8a87` |
| 2026-11-02T21:14:00Z | `c485222f949a` |
| 2026-11-04T05:15:40Z | `7e233b3c1e83` |
| 2026-11-04T06:00:33Z | `58e7e3bdfe8b` |
| 2026-11-05T03:17:03Z | `86de5e1c244b` |
| 2026-11-05T03:46:46Z | `082d0e77cbf0` |
| 2026-11-05T04:45:10Z | `15c797646f4e` |
| 2026-11-05T06:01:30Z | `82c9762a4e61` (last; pre-fix) |

No sync-core comment appears after the fix merged. Silence alone would not
prove anything, because #4370 closed at 2026-11-05T12:51:52Z. Two other facts
show that sync-core kept observing this PR:

- On #4366, sync-core commented at 2026-11-06T13:00:07Z: `Still present on
  stranske/Travel-Plan-Permission#1716 head 3b51e44083d4 (round
  20261106T125940Z)`. In that same round it observed TPP#1716 at a head that
  contains the fix (table in §1) and did not bump #4370 (`fp=08f20d972654`).
- `08c150469cfa` merged about three hours after it was generated, and maint-71
  reported no active finding for it (§2).

## Limits

- The evidence is GitHub state and workflow logs. This run did not execute the
  consumer verifier.
- `isResolved` on the original thread is still `false`. It is recorded as
  superseded (outdated, with the fix delivered and the PR merged), not
  resolved.

## Round 2 verification — 2026-11-09

**Outcome 1: PASS.** Live readback reconfirms generation of the fixed file and
an empty finding report for the exact consumer head
`08c150469cfa35afc9461ba668b8493fdc7a0405`. The operational check is the
existing completed delivery, rather than another regeneration or a consumer
branch edit. The commands in §§1–4 retrieve the acceptance evidence; each
individual read completed in under two minutes. Stop rule for this round:
two repair attempts or 30 minutes, whichever comes first.

| Task / criterion | Rechecked evidence |
| --- | --- |
| T1 / A1 | `gh run list --repo stranske/Workflows --workflow maint-68-sync-consumer-repos.yml` and `gh run view 42433992005 --repo stranske/Workflows --log`; the run is completed/success, its source contains the merged fix, and its Travel-Plan-Permission job records the file update and verified commit in §1. Fetching the consumer file at that exact commit confirms the effective-slot-config lookup on line 8778. |
| T2 | The named REST comment endpoint still returns the allowlist finding; GraphQL identifies thread `PRRT_kwDOPrFQ5c6yXhhx` as outdated and unresolved. Its explicit disposition remains **superseded by the generated fix at `08c150469cfa35afc9461ba668b8493fdc7a0405`**, as recorded in §3. This is an evidence-backed disposition, not a claim of reviewer approval or API resolution. |
| T3 / A2 / A3 | `gh run view 42447027509 --repo stranske/Workflows --log` binds `findings: []`, `raw_active_count: 0`, and `active_review_thread_count: 0` to that same head. Paginated #4370 comments contain no later handoff bump for this finding; §4 explains why comment silence alone is insufficient. The exact-head maint-71 report supplies the positive observation. |

### Reported CI failures

Live readback of [CI Autofix Loop run 42613446920](https://github.com/stranske/Workflows/actions/runs/42613446920)
shows `completed/cancelled`, attempt 1, for PR head
`affbfcc84788b5e6ecb4cc43f929097b806a8d4e`:

- Resolve Context, job `129147387534`: `cancelled`, `steps: []`.
- Record autofix dispatch completion, job `129147401810`: `cancelled`,
  `steps: []`.
- The intervening autofix job was skipped.

Readback command:

```console
gh run view 42613446920 --repo stranske/Workflows --json conclusion,status,jobs,event,headSha,url
```

`gh run view 42613446920 --repo stranske/Workflows --log` returns
`log not found: 129147387534`. No step failure or code diagnostic is available.
The reason for cancellation is unknown; cancellation does not establish a
workflow defect or successful autofix execution. No workflow repair was made.
This update changes only the evidence record; no executable tests apply.
