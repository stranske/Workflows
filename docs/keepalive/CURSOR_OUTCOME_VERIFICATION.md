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
