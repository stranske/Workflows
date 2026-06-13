# Local Opener/Closer Lanes — State, Retention & Steward Contract

This document is the **system-of-record contract** for the local opener/closer
lane automation that drives issue→PR→merge→verify work across the supported
`stranske/*` repos. `CLAUDE.md` requires that system behavior be grounded in an
in-repo document; before this file existed, the lane state/retention/steward
arrangement lived only in the local automation configs under `~/.codex` and in
workspace-private memory, with no owning doc in the system-of-record repo.

> **Editing scope.** The lane *implementation* — the automation TOMLs, the
> `handoff.sh` helper, the rendered Claude prompt `.md` files, the worktree
> reaper — lives under `~/.codex` and is **not** in this checkout. This document
> is authoritative for the *contract* (what the arrangement is and why), but the
> recommended changes to the out-of-repo implementation (moving `workloop-state.md`
> out of repos, building/maintaining a worktree reaper) are recorded here as
> **recommendations**, not implemented in this repository. The only files this
> contract owns in-repo are this doc, the consumer-template `.gitignore` status
> block, `.github/sync-manifest.yml`, `docs/ops/GITNEXUS.md`, and
> `docs/ops/bin/gitnexus_fleet.sh`.

Related docs: [`REPO_REVIEW_PROCESS.md`](REPO_REVIEW_PROCESS.md) (the weekly
evaluator → approved-queue lifecycle the opener consumes) and
[`GITNEXUS.md`](GITNEXUS.md) (the local code-intelligence layer and the
`Workflows-steward` worktree note).

## Lanes overview

Two single-purpose lanes operate across the supported fleet:

- **Opener** — *discover-and-create*. Reads the human-approved queue and live
  fleet issues, then materializes the highest-priority unlinked implementation
  issue as a new issue (when needed) plus a ready-for-review PR. Cap: **at most
  5 active opener-owned PRs** across the whole fleet at any time. Round
  outcomes: `new_issue` | `advance` | `no_op`.
- **Closer** — *cleanup-merge-verify*. Drives existing PRs through
  merge → verify → close → optional bounded follow-up. Round outcomes:
  `merge` | `close` | `followup_only` | `no_op`.

Each lane runs as both a Codex CLI automation and a Claude Code scheduled task;
the two CLIs alternate via a shared baton sentinel (see below). The opener
applies the matching concrete `agent:*` label (`agent:codex` / `agent:claude`)
to the PR it opens — never to the source issue — so that the agent with live
capacity claims the work and natural alternation is preserved.

## State locations

All durable lane state lives under `~/.codex`, outside any repo checkout:

| State | Location | Purpose |
| --- | --- | --- |
| Baton sentinel | `~/.codex/handoff/lane-handoff.json` | Single cross-lane JSON: `baton` (round/chain), `active.*` (most-recent productive action — cross-lane, single-slot), `queue` pressures, `batch.last_sweep`, and `stop.scoped_blockers`. |
| Handoff helper | `~/.codex/bin/handoff.sh` | Subcommands the lanes call: `write-event`, `set-key-pr`/`clear-key-pr`, `scope-blocker`/`clear-scoped-blocker`/`list-scoped-blockers`, `request-pause`/`approve-pause`/`reject-pause`. |
| Pre/post-run relay | `~/.codex/bin/handoff-prerun.sh`, `~/.codex/bin/handoff-relay.sh`, `~/.codex/bin/handoff-postrun.sh` | Lane mutex, structured resume block, and cross-agent dispatch on terminal events. |
| Lane prompts (source) | `~/.codex/automations/<id>/automation.toml` | Codex TOML is the source of truth; `~/.codex/bin/render-claude-prompts.sh` re-renders the Claude `.md` variants under `~/.codex/handoff/prompts/`. |
| Claude scheduled tasks | `~/.claude/scheduled-tasks/handoff-claude-opener/`, `…/handoff-claude-closer/` | The Claude-side scheduled entry points. |
| Per-automation memory | `~/.codex/automations/<id>/memory.md` | Append-only round history (newest section prepended). See rotation policy below. |
| Worktrees | `~/.codex/automations/pd-workloop-resume/worktrees/` and `~/.codex/worktrees/` | Persistent lane worktrees. Disposable clones go under `/tmp`. |
| Per-repo run state | `<repo>/workloop-state.md` | Canonical per-repo lane state (repo, issue, branch, PR, blocker, next action). **Strategy below — should not be tracked.** |

The two lanes (opener `pd-workloop-resume`, closer `imi-merge-verify-closer`)
share the sentinel and hand off via the relay helper. The sentinel's `active.*`
block is **cross-lane and single-slot**: it records the most recent productive
action by either lane, not the full set of in-flight work. Because the opener
cap is 5, the opener routinely has several PRs in flight that `active.*` cannot
represent, so **opener discovery never gates on `active.*`** — it is
informational only.

## Worktree retention tiers

Lane worktrees and disposable clones accumulate under `~/.codex` and `/tmp`. The
intended lifecycle is a four-tier ladder, oldest-first:

1. **live** — a worktree/clone for an in-progress materialization or recovery
   lane. Never reaped while its branch has unpushed work.
2. **reap-eligible** — work pushed and the PR opened/advanced; the local tree is
   no longer needed. Eligible for archival once no process holds it.
3. **compressed** — archived (e.g. tarred/aside) rather than deleted, so the
   next round can recover context if needed. Archive, do not delete, stray
   worktrees/clones.
4. **deleted** — only after compression and a retention window; canonical repos
   are **never** moved or deleted.

Implementation note (out of repo): a worktree reaper is recommended to walk
`~/.codex/**/worktrees` and `/tmp/wf-*`, demoting trees down the ladder by age
and pushed-state. Until that exists, lanes archive rather than delete and run the
code-workspace-hygiene audit when a checkout is created outside a canonical repo.

## `workloop-state.md` strategy

`workloop-state.md` is per-repo lane scratch state (current repo, issue, branch,
PR, blocker, next action), updated at each push and before a round ends. It is a
**lane artifact, not a repo deliverable.**

**Recommendation: not tracked.** The file has historically been committed in
some consumer repos — polluting PR diffs with lane-state churn and merge
conflicts — with mixed per-branch ignore states across the fleet. The in-repo
enabler delivered with this contract:

- `workloop-state.md` is added to the managed status-file block in
  [`templates/consumer-repo/.gitignore`](../../templates/consumer-repo/.gitignore)
  (the `BEGIN/END WORKFLOWS STATUS FILES` region), so it is delivered to every
  consumer repo by `scripts/sync_status_file_ignores.py` — the same mechanism
  that ignores `keepalive_status.md`, `pr_body.md`, and the autofix status
  files. (The whole consumer `.gitignore` is intentionally in the sync-manifest
  `excluded:` list as "repo-specific"; the status-file script owns the managed
  block, which is the correct propagation path for this entry.)
- The sync-manifest exclusion for `.gitignore` therefore remains intentional:
  the generic consumer-template sync must not overwrite repo-local ignore
  rules, while `scripts/sync_status_file_ignores.py --repo <owner/name>` checks
  and reports the managed status block that consumers need. The fallback
  canonical pattern list in that script also includes `workloop-state.md`, so
  the propagation check remains valid even if the template block cannot be
  loaded.

Follow-ups (out of repo, owned by the local automations):

- Stop committing `workloop-state.md` where it is already tracked. A fleet-wide
  `git rm --cached workloop-state.md` is a **fleet operation, not an in-repo
  change**, and is explicitly out of scope here; the gitignore entry above is the
  enabler that makes new commits stop.
- Consider moving lane state out of repos entirely to
  `~/.codex/handoff/workloop/<repo>.md` so it never touches a checkout. This
  removes the artifact from PR diffs at the source and is the recommended
  end-state.

## `Workflows-steward` arrangement

`Workflows-steward` is a **linked git worktree of the canonical Dropbox
`Workflows` clone** that holds the repo-review/steward outputs (the approved
issue queue, the human-decision packet, the repo-review feedback config). The
lane configs and `docs/ops/REPO_REVIEW_BODY_WRITER_PROMPT.md` hardcode steward
paths as the source of approved-queue material, so it is **structurally
load-bearing**, not disposable scratch.

The historical framing ("temporary automation state, must be ignored") is
misleading: it described GitNexus's *indexing* policy (GitNexus should not index
the steward worktree — that remains true) but read as "the steward is
throwaway." The real risk is the opposite. If the steward worktree has `main`
checked out, the **canonical clone cannot `git checkout main`** — git refuses a
branch already checked out in another worktree — so a "temporary" worktree ends
up holding the default branch hostage.

**Canonical arrangement: the `Workflows-steward` worktree should sit at a
detached `HEAD` at `origin/main`.** A detached HEAD takes no branch lock, so the
canonical clone keeps `main` free while the steward still tracks the latest
reviewed tip. GitNexus continues to ignore the steward worktree for indexing —
that part of the old note is correct and is preserved; only the "temporary /
throwaway" framing is corrected (see [`GITNEXUS.md`](GITNEXUS.md),
`docs/ops/bin/gitnexus_fleet.sh`, `AGENTS.md`, and `CLAUDE.md`).

## Memory-file rotation

Each automation keeps an **append-only** `memory.md` under
`~/.codex/automations/<id>/`. The contract:

- Each round **prepends** a new `## <ISO timestamp>` section at the top; existing
  entries are never modified or removed. The file is history — destructive
  rewrites lose context the next round needs.
- The pre-run helper emits only the **last few** entries in its structured
  resume block (older history trimmed for output size); the full file remains on
  disk.
- Rotation, when needed, is by archiving the tail of the file (oldest sections)
  to a dated sibling under the automation directory rather than truncating in
  place — same archive-don't-delete principle as the worktree tiers above.
