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
(`#1836`, `#2210`, `#2415`); `#2470` is a hybrid that stamps a marker into the
body and appends a recovery comment. Check the `Update style` column before
assuming append-versus-rewrite handling. Either way, **the issue itself is the
dashboard**: do not close it during routine triage. Each controller has its own
lifecycle; for example, closing the active `#1836` campaign queue stops that
controller's work, while `#2470` is recreated only through its
failure-notification path.

---

## Current durable trackers

| Issue | Title | Source workflow | Cadence | Update style |
|-------|-------|-----------------|---------|--------------|
| [#2211](https://github.com/stranske/Workflows/issues/2211) | Agent metrics weekly summary | [`agents-weekly-metrics.yml`](../../.github/workflows/agents-weekly-metrics.yml) | Mondays 06:00 UTC | New comment per run |
| [#1836](https://github.com/stranske/Workflows/issues/1836) | Sync/Dependabot campaign queue | [`maint-82-sync-dependency-campaign.yml`](../../.github/workflows/maint-82-sync-dependency-campaign.yml) + [`.github/scripts/sync_dependency_campaign.js`](../../.github/scripts/sync_dependency_campaign.js) | Every 6h + Mondays 10:30 UTC | Body rewritten in place |
| [#2210](https://github.com/stranske/Workflows/issues/2210) | 🔄 Consumer repo drift detected | [`health-68-consumer-sync-drift.yml`](../../.github/workflows/health-68-consumer-sync-drift.yml) | Daily 05:10 UTC | Body rewritten in place |
| [#2470](https://github.com/stranske/Workflows/issues/2470) | 🚨 Integration-Tests Sync Failed - Action Required | [`maint-69-sync-integration-repo.yml`](../../.github/workflows/maint-69-sync-integration-repo.yml) | On qualifying template/config pushes or manual dispatch | Stuck-window marker in body + recovery comment |
| [#2415](https://github.com/stranske/Workflows/issues/2415) | 📊 LangSmith Trace Coverage Dashboard | [`maint-80-langsmith-metrics-dashboard.yml`](../../.github/workflows/maint-80-langsmith-metrics-dashboard.yml) | Mondays 09:00 UTC + manual dispatch | Body rewritten in place |

The signal flow each tracker carries:

- **#2211** — health check on the weekly metrics pipeline. Healthy state is `Parse errors: 0` and non-zero terminal disposition records. A regression here usually means a producer is emitting a malformed artifact, not that the dashboard itself is broken.
- **#1836** — work queue for items the local Codex watcher should claim. The body holds the live queue state with a sync hash, repo counts, and per-item status. Active campaigns must not be closed; the controller treats a closed campaign as "stop work."
- **#2210** — fan-out drift report across registered consumer repos. `Health 68` creates or refreshes it when drift is detected; a clean run does not close it, so its latest body must be read as the last detected signal rather than an automatic current-status promise.
- **#2470** — stuck-window marker for the integration-repo template sync. A `<!-- sync-tracker-stuck-window:v1 ... -->` marker in the body means the sync is currently failing. The next successful non-dry run with a sync token strips the marker and appends a `✅ Integration sync recovered` comment, but never closes the issue, so a marker-free body carrying a recovery comment is the healthy resting state. The `Resolution Steps` list in the issue body still says "Close this issue once the next run succeeds"; that line predates the stuck-window marker and does not reflect how `maint-69` actually treats the tracker.

### Superseded tracker numbers

A controller re-mints its tracker if the previous one is closed, so tracker
numbers change over time. Numbers that appear in older comments and commits:

| Controller | Superseded | Current |
|------------|-----------|---------|
| `agents-weekly-metrics.yml` | [#1796](https://github.com/stranske/Workflows/issues/1796) — closed 2026-08-01 as a duplicate; last comment 2026-05-25 | [#2211](https://github.com/stranske/Workflows/issues/2211) |
| `health-68-consumer-sync-drift.yml` | [#1868](https://github.com/stranske/Workflows/issues/1868) — closed 2026-05-14 | [#2210](https://github.com/stranske/Workflows/issues/2210) |

When a controller's tracker is replaced, update the table above in the same
change so this page never points at a closed issue.

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
  Close only when retiring the underlying controller, or when the tracker is a
  proven duplicate of a newer one for the same controller (see *Superseded
  tracker numbers* above — the surviving tracker must stay open).
- **Read the latest comment / body**, not the original creation body. The
  original snapshot is frozen at issue creation; current state lives further
  down (or in the rewritten body for `#1836` / `#2210` / `#2470`).
- **A red signal** (parse errors > 0 in `#2211`, drift count > 0 in `#2210`,
  a stuck-window marker present in `#2470`,
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
- `📊 LangSmith Trace Coverage Report - Week of <date>` — **retired format.**
  `maint-80-langsmith-metrics-dashboard.yml` used to mint one issue per
  schedule; it now upserts the single
  [#2415](https://github.com/stranske/Workflows/issues/2415)
  `📊 LangSmith Trace Coverage Dashboard` instead. The dashboard lookup matches
  that exact title, so leftover `Report - Week of …` issues are unreachable by
  the controller and were closed on 2026-08-01 (#2213, #2247; #2194 earlier).

Rule of thumb: if the title carries a counter or a fixed timestamp ("expires
in 39 hours", "run 235"), it is **transient**. If the title is generic and the
body is a recurring snapshot ("queue", "summary", "drift detected"), it is
**durable**.

---

## See also

- [`CONSUMER_REPO_MAINTENANCE.md`](CONSUMER_REPO_MAINTENANCE.md) — context for `#2210` (consumer drift) and the `Maint 68` sync surface.
- [`REPO_REVIEW_PROCESS.md`](REPO_REVIEW_PROCESS.md) — the repo-review pipeline emits its own evidence trail; it does not currently use a durable tracker, but the same "do not triage automated review evidence as work" rule applies.
