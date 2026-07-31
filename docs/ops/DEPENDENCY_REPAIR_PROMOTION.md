# Dependency Repair Promotion

Dependency updates use two ownership lanes:

1. A clean Renovate or Dependabot pull request stays bot-owned.
2. A coding-agent repair runs on an agent-owned pull request, not as an
   unclassified commit added to the bot branch.

This preserves the useful part of local coding agents: they still diagnose and
repair dependency failures. The extra cost is one replacement pull request for
a dependency-coupled repair and a small provenance check. In return, reviewers
can distinguish the dependency delta from the repair, source-template feedback
cannot be hidden inside a mutated bot branch, and the cleanup automation can
make the same decision without a human reconstructing commit history.

## Choose the repair lane

Classify the failing work before editing a branch:

- **Dependency-independent repair:** Create a companion PR from current `main`.
  Merge it, then ask Renovate to rebase/retry the original dependency PR.
- **Dependency-coupled repair:** Create an `agent/deps-repair-*` promotion PR
  from current `main`. Its first commit must contain only the selected,
  classified bot dependency delta. Put the coding-agent repair in later
  commits.
- **Shared Workflows/template repair:** Fix `stranske/Workflows` first and let
  consumer sync replace the consumer PR.
- **Owner decision:** Stop only for unknown/security-sensitive dependencies or
  a repair that changes product semantics.

When a bot PR already contains non-bot commits, inspect each unclassified
commit before closing it. Preserve useful dependency-independent work in a
companion PR. Do not copy broad workflow/template edits merely to avoid losing
them; source-owned changes belong in Workflows and should be re-derived from
the actual review or failure.

## Prepare a promotion PR

Start from a fresh clone or worktree. Let `SOURCE_BASE` be the first parent of
the selected bot-owned commit prefix and `SOURCE_HEAD` be the last classified
bot/generated commit to reproduce.

```bash
git fetch origin main "pull/${SOURCE_PR}/head:source-pr-${SOURCE_PR}"
git switch -c "agent/deps-repair-${SOURCE_PR}" origin/main
PROMOTION_BASE="$(git rev-parse HEAD)"
git diff --binary "$SOURCE_BASE" "$SOURCE_HEAD" | git apply --index --3way
git commit -m "chore(deps): reproduce bot delta from #${SOURCE_PR}"
git push -u origin "agent/deps-repair-${SOURCE_PR}"
```

If the patch does not apply cleanly, first ask Renovate to rebase/recreate the
dependency PR. Do not mix conflict repair into the provenance commit.

Include this single-line marker in the promotion PR body, using full commit
SHAs:

```text
<!-- dependency-repair-promotion:v1 {"source_pr":123,"source_base_sha":"...","source_head_sha":"...","promotion_base_sha":"..."} -->
```

After the promotion PR exists, close the superseded bot PR with a link to the
replacement. Coding agents may then commit the bounded repair on the promotion
branch. The PR remains attributable to dependency automation through
`workflow:source-dependabot` and identifiable through
`dependency:repair-promotion`.

A structurally valid promotion marker is itself explicit dependency source
context, so keepalive can dispatch the coding agent without a linked issue or a
manually applied source label. PR 46 still validates the referenced bot PR,
commit ancestry, and patch identity before the promotion can merge.

## Machine-enforced contract

`PR 46 Dependency Repair Contract` runs only for dependency-bot PRs and marked
promotion PRs.

For bot PRs, it permits:

- Renovate or Dependabot commits; and
- GitHub Actions lockfile regeneration commits only when both the commit
  subject and every changed path match the strict generated-lockfile allowlist.

Other commits fail the check as unclassified and must be split into a companion
or promotion PR.

For promotion PRs, it verifies:

- agent ownership and the `agent/deps-repair-*` branch prefix;
- a valid source bot PR and a source commit prefix containing no unclassified
  commits;
- the recorded source and promotion base relationships;
- a stable patch identity and identical changed-path set between the selected
  bot delta and the first promotion commit.

Later commits are deliberately allowed: those commits are where local coding
agents provide the repair. Normal CI, active review-thread checks, shared
template ownership, and dependency security review still apply.
