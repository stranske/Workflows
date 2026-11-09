# Cursor post-merge outcome evidence

After the fix PR merges, collect the PR-search component of the production
acceptance criterion with the read-only local command:

```bash
python scripts/check_cursor_pr_outcome.py --fix-pr stranske/Workflows#4564
```

The command searches all PR states authored by `app/github-actions` under the fix
repository's owner, excluding owner-excluded `stranske/Collab-Admin`. It reads
actual PR heads and selects `cursor/issue-<N>-<slug>` branches. Bare
`cursor/issue-<N>` bootstrap branches are excluded. Creation timestamps must fall
within the 14 days starting at the fix PR's merge, including both boundaries.
The broader search avoids relying on branch-prefix search or PR-body mentions.

Retain the JSON output with the run evidence. Exit 1 means a matching PR was
found; exit 2 means the window is pending or evidence is unavailable. Exit 0
establishes only an empty, complete search window. Incomplete search results,
pagination gaps, changing counts and the search API's 1000-result cap cannot
produce a clear result. Run this after GitHub search has indexed recent PRs.

The acceptance checkbox stays unchecked until the full window has elapsed **and**
the next keepalive target that merges during `Run Cursor` has been observed.
Record that target's PR URL, merge timestamp, run URL, `Run Cursor` start/end
timestamps, and the closed-target guard's skip result and retained commit SHAs.
The search command does not establish that event or prove its ordering. Local
tests and an empty search before deployment do not satisfy production acceptance.

To check a candidate event's timing and job steps, add the target PR and the
numeric **job ID** (rather than the run ID):

```bash
python scripts/check_cursor_pr_outcome.py --fix-pr stranske/Workflows#4564 \
  --target-pr OWNER/REPO#NUMBER --job-id JOB_ID
```

This reads the target PR and the job in that target's repository. It requires a
successful completed job, a merge strictly between the `Run Cursor` start/end
timestamps after deployment and within the observation window, a subsequent
successful `Check target PR before pushing` step, and a skipped `Commit and push
changes` step. Equal merge/step timestamps are ambiguous and cannot establish
ordering. Invalid or unavailable evidence exits 2; valid timing does not shorten
the 14-day search window or change a search regression into success.

The `timing_verified` record is a candidate event, not full acceptance. Job
metadata does not identify the checked-out target reliably for dispatched
keepalive runs. To verify the source-issue receipt as well, supply its numeric
comment ID (the `issuecomment-ID` portion of its URL):

```bash
python scripts/check_cursor_pr_outcome.py --fix-pr stranske/Workflows#4564 \
  --target-pr OWNER/REPO#NUMBER --job-id JOB_ID --receipt-comment-id COMMENT_ID
```

This uses Node and the workflow's actual `extractIssueNumberFromPull` resolver
to require a workflow-bot comment on the resolved source issue. The receipt
must be unedited and created during the guard step; its marker, target PR,
run URL and skip outcome must match the candidate. The JSON retains the receipt
URL, source issue and reported full commit SHAs (or an explicit empty list).
These are reported SHAs, not independent proof of the commits' contents.
Invalid receipts cannot establish the target/run association and exit 2.

Also establish that this was the **next** eligible mid-run merge; supplying a
later convenient job does not prove that condition. Even a valid receipt leaves
that ordering requirement explicit and cannot shorten the observation window.
