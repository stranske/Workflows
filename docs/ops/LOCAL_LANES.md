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
> changes to the out-of-repo implementation (moving `workloop-state.md`
> out of repos, the worktree reaper, memory-file rotation) are **implemented in the
> `~/.codex` layer as of 2026-06-13** but live outside this checkout — this doc records
> the contract and current status, not the code. The only files this
> contract owns in-repo are this doc, the consumer-template `.gitignore` status
> block, `.github/sync-manifest.yml`, `docs/ops/GITNEXUS.md`, and
> `docs/ops/bin/gitnexus_fleet.sh`.

Related docs: [`REPO_REVIEW_PROCESS.md`](REPO_REVIEW_PROCESS.md) (the weekly
evaluator → approved-queue lifecycle the opener consumes) and
[`GITNEXUS.md`](GITNEXUS.md) (the local code-intelligence layer and the
`Workflows-steward` worktree note).

## Lanes overview

Updated 2026-11-17. The full owner-facing design is `Audits/closer-lane-2026-11/design/lane-design.html`
(+ `.pdf`) in the owner's workspace; `stranske/Orchestrator` `ARCHITECTURE.md` summarises the boundary.
Three deterministic Python lanes run across the supported fleet, started by one controller pass:

- **Controller pass** — `~/.codex/automations/reviewed-repo-automation-controller/controller.py`. Fired by
  three seats that share one stamp (`~/.codex/orchestrator/controller-last-pass.json`): the Codex automation,
  the Claude scheduled task `lane-controller-seat`, and launchd `com.stranske.controller-seat` as a backstop.
  Each pass starts detached rounds of the lanes, then the one owner notification.
- **Opener** (`opener-core`) — judges and starts EXISTING actionable issues (it does not create issues).
  Cap: at most 8 opener-owned PRs not yet in the closer's hands. A cheap judge decides start / park / done
  (rewriting a body that fails AGENT_ISSUE_FORMAT); the router chooses the agent and the mode, local first
  while fewer than 3 local agents are busy, otherwise hosted keepalive via the `agent:*` label. In invite-mode
  repos it opens the bootstrap PR itself. It watches each start (one retry with another agent, then park) and
  offers a few issues a day to the experiment producer.
- **Local loop** (`local_loop.py`) — drives a local start's PR (`agents:local-loop`) round by round on CI
  results, rotates the agent after two unproductive rounds, and hands the PR to hosted keepalive if it stalls.
- **Closer** (`closer-core`) — drives agent PRs through merge → verify → close (and, since 2026-11-16, PRs a
  Claude Code session made that name no issue: a `claude.ai/code/session_` link in the body is adopted after 30
  minutes without a push, the Claude Code footer or `workflow-source:local_request` after 7 days; each is
  judged once per head and merged through merge_guard), rotates stalled agents with
  `agent:auto`, files bounded follow-up issues, parks a non-converging chain as a `[backlog]` issue, and keeps
  the owner's needs-human catalog (each parked item gets a cause and a condition; untouched items close after
  30 days). Merges go through the exact-head merge rail, which runs a task's own acceptance commands on the
  exact head when the PR claims a deliberate break (Gate applies the `acceptance-criteria` label).
  **Reopened issues (since 2026-11-17):** when the post-merge runtime-AC check reopens an issue
  (`runtime-ac:reopened`) and its linked open PR is only a bootstrap stub (green or behind, keepalive reporting
  tasks complete), the closer runs the issue's acceptance commands on the default branch head instead of judging
  the stub: a pass with a named test closes the issue as met and closes the stub (the reopen was environmental);
  a failure starts a repair round on the stub's branch with the reopen's failing output attached; an unrunnable
  check falls back to the ordinary path. The runtime-AC check builds its venv the way CI does
  (`requirements.lock` plus the `app`/`dev` extras), so it fails only where CI would (Orchestrator#1439).
- **Sync** (`sync-core`) — classifies generated sync PRs, files one handoff issue per finding, nudges Maint 71
  when a ready PR waited past its grace and may dispatch a Maint 68 refresh. It never merges: Maint 71 is the
  only merger of sync PRs and Maint 82 is its timed continuation queue.

Holds: the opener skips `agents:paused`, `needs-human`, `intake:held` and `do-not-merge` (and ops-alert
issues); the closer skips `agents:paused`, `agent:paused`, `needs-human`, `do-not-merge`, `hold`,
`agents:auto-pilot-pause`, `goal-drift` and `tracker:durable`. Agent families and their model per tier come from
`.github/agents/model-table.json` (shared by local and hosted runs); hosted runner receipts record the
requested and reported model.

**Retired (kept below for history):** the Codex prompt lanes `pd-workloop-resume` / `imi-merge-verify-closer`,
the Claude tasks `handoff-claude-opener` / `handoff-claude-closer`, and the baton relay
(`lane-handoff.json`, `handoff-relay.sh`, `handoff-prerun.sh`).

## State locations

Current lane state lives under `~/.codex`, outside any repo checkout:

| State | Location | Purpose |
| --- | --- | --- |
| Controller stamp | `~/.codex/orchestrator/controller-last-pass.json` | Last pass time; seats fire only when it is stale. |
| Lane rounds | `~/.codex/orchestrator/<core>/rounds.jsonl` (`opener-core`, `closer-core`, `sync-core`) | One line per round; read by the value-chain monitor. |
| Lane ledgers | `~/.codex/orchestrator/opener-core/targets/`, `~/.codex/orchestrator/closer-core/` | Per-target state (starts, links, parks; closer outcomes). |
| Lane config | `~/.codex/opener-core/config.json`, `~/.codex/closer-core/`, `~/.codex/sync-core/config.json` | Caps and switches. |
| Owner catalog | `~/.codex/orchestrator/closer-core/needs-human.md` | The single list of items that need the owner. |
| Capacity sheds | `~/.codex/handoff/capacity-shed/<agent>` | An agent stood down after a provider limit, until its reset. |

Retired state (no longer written): the baton sentinel `~/.codex/handoff/lane-handoff.json` (the controller
still reads its legacy `stop.scoped_blockers` only), the relay helpers, and the per-automation `memory.md` files
of the retired prompt lanes.

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

Implementation note (out of repo, implemented 2026-06-13): `~/.codex/bin/lane-worktree-gc.sh`
(daily launchd `com.stranske.lane-worktree-gc`) removes lane worktrees idle ≥14 days,
freshness-gated via `find -newer` so an in-flight tree is never deleted, and best-effort
prunes the canonical repos' worktree registrations. It is dry-run by default; `--apply`
reclaims (the first apply reclaimed ~43 GB). Canonical repos are never moved or deleted.

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
  files. The validator itself is copy-synced to `scripts/sync_status_file_ignores.py`
  so the command named in the managed block exists in every consumer. Applying
  the block also removes repo-local copies of `node_modules/` and writes one
  canonical all-depth rule. Targeted exceptions for `.github/scripts/node_modules`
  are retained only when that consumer's `.github/scripts/package.json` declares a
  `file:node_modules/` dependency; registry-installed consumers keep the tree ignored.
  The local `--check`, `--apply`, and `--print-block` paths all inspect that package
  manifest before selecting the managed block, so printed repair output cannot
  reintroduce vendored-tree exceptions into a registry-installed consumer.
  This keeps ordinary nested installs ignored without hiding a deliberately vendored
  workflow dependency. (The whole consumer `.gitignore`
  is intentionally in the sync-manifest
  `excluded:` list as "repo-specific"; the status-file script owns the managed
  block, which is the correct propagation path for this entry.)
- The sync-manifest exclusion for `.gitignore` therefore remains intentional:
  the generic consumer-template sync must not overwrite repo-local ignore
  rules, while `scripts/sync_status_file_ignores.py --repo <owner/name>` checks
  and reports the managed status block that consumers need. The fallback
  canonical pattern list in that script also includes `workloop-state.md`, so
  the propagation check remains valid even if the template block cannot be
  loaded.

Implemented in the out-of-repo lane layer (2026-06-13):

- **Lane state relocated out of repos entirely** to `~/.codex/handoff/workloop/<repo>.md`,
  so it never touches a checkout. The opener/closer prompts now write there and are
  forbidden from creating or committing `workloop-state.md` inside any repo;
  `handoff.sh read-resume` reads the relocated path (with an in-repo fallback during the
  transition). This removes the artifact from PR diffs at the source — the recommended
  end-state, now live.

Still pending as a fleet operation (not an in-repo change here):

- A one-time `git rm --cached workloop-state.md` for the repos where it is already tracked
  (`Travel-Plan-Permission`, `Trend_Model_Project`, `Counter_Risk`, `Manager-Database`,
  `Inv-Man-Intake`, `trip-planner`, `learning-management-system`). This is the documented
  follow-up to the gitignore enabler above; it stops the tracked copies from lingering once
  the lanes have stopped writing them.

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

**Canonical arrangement (applied 2026-06-13): the `Workflows-steward` worktree sits at a
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
- Rotation is implemented (2026-06-13) by `~/.codex/bin/rotate-lane-memory.sh` (daily
  launchd `com.stranske.lane-memory-rotate`): it keeps the newest 30 sections in `memory.md`
  and archives the older tail to a dated `memory-YYYY-MM.md` sibling, md5-guarded against a
  concurrent prepend so a new round's entry is never clobbered — archive-don't-delete, same
  principle as the worktree tiers above.
