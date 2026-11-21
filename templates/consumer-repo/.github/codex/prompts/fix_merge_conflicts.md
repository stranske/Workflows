# Fix Merge Conflicts

Integrate the PR's actual base into its head branch. Preserve the intent of both sides and limit changes to the merge and any fixes it requires.

## Inspect the merge state first

```bash
git ls-files --unmerged
git rev-parse -q --verify MERGE_HEAD
```

- If `MERGE_HEAD` exists, continue that merge. Preserve its staged changes and incoming commit. Do not merge again, abort, reset or rebase. With unmerged entries, resolve those paths. With an empty unmerged index, proceed directly to verification and finalization, even if the index matches `HEAD`.
- If there are unmerged entries without `MERGE_HEAD`, identify the operation in progress with `git status` and report it. Preserve that state and do not start a merge.
- Only if both checks show no pending merge or unmerged paths, follow the base check below. An inspection error is a blocker.

## Check the base when no merge is pending

Verify the checkout is the intended PR head and check `git status` for other operations or edits that a merge could disturb. Select the first available base from this order.

1. `GITHUB_BASE_REF` from the PR workflow.
2. `WORKFLOW_BASE_REF` from the runner's `base_ref` input or PR event when exposed to the session.
3. The base explicitly supplied by the standalone caller, then verified metadata for the current PR.
4. The branch named by `git symbolic-ref --short refs/remotes/origin/HEAD`, only when confirmed as the intended target. A standalone caller can explicitly request the default branch.

If the selected base conflicts with known PR metadata or the target cannot be established, report the blocker. Use the remote that serves the verified base repository, typically `origin`. Set `base_remote` to that remote and `base_branch` to the selected branch name without a `refs/heads/` prefix.

```bash
git fetch --no-tags -- "$base_remote" "refs/heads/$base_branch" || exit 2
git merge-base --is-ancestor FETCH_HEAD HEAD
```

Exit 0 from the ancestry check means the fetched base is already integrated. Report that no merge is required. Ensure the relevant history is available before relying on exit 1 in a shallow checkout. With exit 1 and sufficient history, run `git merge --no-commit --no-ff FETCH_HEAD` once. Reinspect the index and `MERGE_HEAD`. Continue a pending merge and report any other merge failure with its diagnostics. Report fetch or ancestry errors and stop before merging.

## Resolve and verify

- Read the conflicting hunks and the surrounding code. Combine compatible changes and adapt PR code, tests and documentation to any changed base contracts. Preserve coverage contributed by either side.
- Keep the PR version of `pr_body.md` and `ci/autofix/history.json` when they conflict, following the repository's branch-specific merge rules.
- Remove conflict markers and stage only the resolved paths, including intended deletions. Confirm `git ls-files --unmerged` returns no entries, inspect the resolved files, and run `git diff --check` and `git diff --cached --check`.
- Run the relevant project tests using the repository's documented commands. Preserve test output and exit status. Report failures or any tests you could not run.

## Finalize the verified merge

- **Reusable runner:** Stage the resolutions and leave the verified merge pending with `MERGE_HEAD` intact, including a clean merge with no staged diff. The runner's commit-and-push step finalizes the merge and publishes it to the PR branch.
- **Standalone:** Complete the verified pending merge with a descriptive merge commit, even with no staged diff. Confirm the commit has the original PR head and the pending incoming commit as parents. Publish only when the caller has authorized it, through the normal fast-forward update to the verified PR head branch.

Report the base or incoming commit, the resolution and test results, and whether the merge was unnecessary, left for runner finalization, or committed locally. Never force-push.
