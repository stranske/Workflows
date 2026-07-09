# Durable Tracking Issues

A small number of GitHub issues in this repo are **durable trackers**: a single
issue that an automation re-uses across many cycles. These issues stay open by
design. They are not work items to be triaged, assigned, or closed during normal
sweeps — they are dashboards or queues whose lifetime is tied to the underlying
controller, not to a single fix.

This page lists the current durable trackers, explains how to recognize them,
and tells automations and humans how to treat them.

---

## Why this exists

Several scheduled workflows produce a recurring report (drift, queue state,
metrics summary). Without a tracker convention each run would either:

- Open a fresh issue every cycle (rapidly creating dozens of duplicates), or
- Have no surfaced state at all.

The trackers below solve this by reusing one issue per controller. The bot
either appends a comment per cycle (`#2211`) or rewrites the body in place
(`#1836`, `#1868`). Either way, **the issue itself is the dashboard** — closing
it does not advance any work; the controller will simply re-create one on the
next cycle.

---

## Current durable trackers

| Issue | Title | Source workflow | Cadence | Update style |
|-------|-------|-----------------|---------|--------------|
| [#2211](https://github.com/stranske/Workflows/issues/2211) | Agent metrics weekly summary | [`agents-weekly-metrics.yml`](../../.github/workflows/agents-weekly-metrics.yml) | Mondays 06:00 UTC | New comment per run |
| [#1836](https://github.com/stranske/Workflows/issues/1836) | Sync/Dependency campaign queue | [`maint-82-sync-dependency-campaign.yml`](../../.github/workflows/maint-82-sync-dependency-campaign.yml) + [`.github/scripts/sync_dependency_campaign.js`](../../.github/scripts/sync_dependency_campaign.js) | Every 6h + Mondays 10:30 UTC | Body rewritten in place |
| [#1868](https://github.com/stranske/Workflows/issues/1868) | 🔄 Consumer repo drift detected | [`health-68-consumer-sync-drift.yml`](../../.github/workflows/health-68-consumer-sync-drift.yml) | Daily 05:10 UTC | Body rewritten in place |

The signal flow each tracker carries:

- **#2211** — health check on the weekly metrics pipeline. Healthy state is `Parse errors: 0` and non-zero terminal disposition records. A regression here usually means a producer is emitting a malformed artifact, not that the dashboard itself is broken.
- **#1836** — work queue for items the local Codex watcher should claim. The body holds the live queue state with a sync hash, repo counts, and per-item status. Active campaigns must not be closed; the controller treats a closed campaign as "stop work."
- **#1868** — fan-out drift report across registered consumer repos. Auto-resolves on the next clean `Maint 68` run; the closure happens in the workflow, not by hand.

---

## How automations should treat these

Automations that scan open issues for triage, assignment, or "stale" closure
should **filter out** durable trackers. Recommended filters in order of
robustness:

1. `label:tracker:durable` — applied to all current trackers as a stable
   programmatic signal.
2. `label:automated` or `label:automation` — broader, catches other auto-bot
   issues too. Useful as a safety net when `tracker:durable` is missing.
3. Title prefix conventions (`🔄`, `⚠️`) and repeating titles — least reliable;
   use only as a backstop.

When adding a new automation that creates a durable tracker, apply
`tracker:durable` at issue creation and add a row to the table above in the
same change.

---

## How humans should treat these

- **Do not close them as part of routine triage**, even if the latest comment
  looks "stale" — the controller may have nothing to report on a quiet day.
  Close only when retiring the underlying controller.
- **Read the latest comment / body**, not the original creation body. The
  original snapshot is frozen at issue creation; current state lives further
  down (or in the rewritten body for `#1836` / `#1868`).
- **A red signal** (parse errors > 0 in `#2211`, drift count > 0 in `#1868`,
  unclaimed `needs-local-codex` items in `#1836`) means the underlying system
  needs attention — but the fix lands in code or in another repo, not by
  closing the tracker.
- **The tracker is not the work item.** If you discover real follow-up work from
  reading a tracker, file a *new* issue against the affected workflow or script
  and reference the tracker; do not co-opt the tracker for that work.

---

## Distinguishing trackers from transient alerts

Some auto-bot issues *are* normal work items and should be closed when
addressed. Examples:

- `⚠️ CODEX_AUTH_JSON expires in N hours` — transient alert, fresh issue per
  expiry window. Close after token rotation.
- `🔴 Integration CI failed (run N)` — single-incident issue, close after the
  branch / fix lands.

Rule of thumb: if the title carries a counter or a fixed timestamp ("expires
in 39 hours", "run 235"), it is **transient**. If the title is generic and the
body is a recurring snapshot ("queue", "summary", "drift detected"), it is
**durable**.

---

## See also

- [`CONSUMER_REPO_MAINTENANCE.md`](CONSUMER_REPO_MAINTENANCE.md) — context for `#1868` (consumer drift) and the `Maint 68` sync surface.
- [`REPO_REVIEW_PROCESS.md`](REPO_REVIEW_PROCESS.md) — the repo-review pipeline emits its own evidence trail; it does not currently use a durable tracker, but the same "do not triage automated review evidence as work" rule applies.
