# Workflows: Development History

This document summarizes the phases of development the repo has gone through
since launch. It is meant to give a new contributor (or future-you) a quick
read on how the system grew, what it could and couldn't do at each point,
and where it stands now. It is complementary to [`CHANGELOG.md`](../CHANGELOG.md)
(per-release records) and the operational docs under [`docs/ops/`](ops/).

The phase boundaries below are anchored at points where commit cadence dropped
sharply — i.e. moments when a development push ended and the system entered a
period of relatively stable use. Phase 4 in particular contains a six-week
quiet stretch where the system was used by consumers without active rebuilds.

---

## Timeline at a glance

| Phase | Date range | Commits | Workflow files | Tests | Tag landed | Defining work |
|---|---|---:|---:|---:|---|---|
| 1. Bootstrap & v1.0 buildout | 2025-12-16 → 2026-01-12 | 958 | 0 → 81 | 164 | `v1.0.0` (12-16) | First reusable workflows, manifest-driven consumer sync, auto-pilot, Codex belt |
| 2. v1.1.x release & first Feb push | 2026-01-13 → 2026-02-10 | 832 | 81 → 94 | 229 | `v1.1.0`/`v1.1.1`/`v1.1.2` (1-26 → 1-31) | Verifier follow-up pipeline, GitHub-App token minting, sync-quality surveillance triad |
| 3. Feb consolidation push | 2026-02-11 → 2026-02-28 | 413 | 94 → 98 | 232 | — | Claude becomes first-class agent, agent-agnostic belt rename, LangSmith integration, +4 consumers |
| 4. Production quiet | 2026-03-01 → 2026-04-11 | 45 | 98 → 99 | 232 | — | PR-health scanner subsystem, Claude code-review opt-in, real consumer use without rebuilds |
| 5. Post-quiet re-engagement | 2026-04-12 → 2026-04-29 (current) | 240 | 99 → 101 | 260 | — | Repo-review subsystem, sync/Dependabot campaign queue, action-pin contract, Python 3.12 fleet pin, durable-tracker convention |

Counts cover the period through commit `e0d04b6c` on 2026-04-29. Workflow file
counts are `.github/workflows/*.yml` only; test counts are
`tests/**/*.py` + `.github/scripts/__tests__/*.test.js`. The full snapshot of
every dimension is at the foot of this doc under
[Where the repo stands now](#where-the-repo-stands-now).

---

## Phase 1 — Bootstrap & v1.0 buildout (Dec 16, 2025 → Jan 12, 2026)

**Endpoint commit**: [`4502bdb3`](https://github.com/stranske/Workflows/commit/4502bdb3) — 958 commits in 4 weeks.

**What worked**: From a standing start the repo shipped 81 workflow files and
the first reusable contract (`reusable-10-ci-python.yml`, `reusable-codex-run.yml`,
`reusable-70-orchestrator-init.yml`, `reusable-70-orchestrator-main.yml`). The
auto-pilot pipeline (issue → PR → keepalive → verify → follow-up) landed by
phase end via the Phase 4C work in PR #740. Manifest-driven consumer sync via
`maint-68-sync-consumer-repos.yml` arrived on 2025-12-28 (#252) and seven
consumer repos were registered: Travel-Plan-Permission, Template, trip-planner,
Manager-Database, Portable-Alpha-Extension-Model, Trend_Model_Project, and
Collab-Admin.

**Agent footprint**: Codex was dominant from day one (~542 mentions across
workflow YAML). Copilot was present for auto-label and dedupe-comment guards
(~17 mentions). Claude appeared only as scattered string references — no
dedicated runner.

**Consumer CI**: Median Gate run **234s (3.9 min)**, p90 257s. Sample skewed to
Trend_Model_Project (~250s) and Manager-Database (~70–160s); the band was tight
because consumer load was light and the workflow set was new.

**Pain points**: First CODEX_AUTH_JSON expiry incident (#706, Jan 9) — closed
same day, but the start of a long series. Continuous wave of consumer-drift
issues (~7 between Dec 26 and Jan 12). README declared "Production Ready"
before the verifier had its full follow-up pipeline; tests count was higher in
the README than what was on disk (188+128 figure included fixtures).

**What it couldn't do yet**: Publish from a single tagged release reliably
(floating `v1` tag plumbing didn't ship until Phase 2), auto-resolve
verification feedback (verify→follow-up issue pipeline ships in Phase 2),
balance API rate-limits at scale (GitHub App token minting expanded fleet-wide
in Phase 2).

**End-of-phase backlog**: 10 open issues, 0 open PRs.

---

## Phase 2 — v1.1.x release & first Feb push (Jan 13 → Feb 10, 2026)

**Endpoint commit**: [`c93c6204`](https://github.com/stranske/Workflows/commit/c93c6204) — 832 commits in 4 weeks.

**What worked**: Three release tags shipped in five days at the start (`v1.1.0`
on 1-26, `v1.1.1` on 1-30, `v1.1.2` on 1-31). The verify→follow-up pipeline
landed (`agents-verify-to-issue.yml`, `agents-verify-to-new-pr.yml`,
`agents-verify-to-new-pr-autopilot.yml`). Sync-quality surveillance triad
arrived: `health-68-consumer-sync-drift.yml`, `health-73-template-completeness.yml`,
`health-74-template-drift.yml`, plus `health-75-api-rate-diagnostic.yml` for
rate-limit observability. GitHub-App token minting was extended to all 78
workflows on 2026-02-02 (#1197) — this was the phase-defining rate-limit fix.
COMPATIBILITY.md and the floating-`v1` tag plumbing landed
(`maint-73-refresh-reusable-tags.yml`).

**Agent footprint**: Codex 582, Copilot 20 (steady), Claude growing fast (15 →
55 mentions). The optimizer switched to Claude Sonnet 4.5 mid-phase (#1312);
LangChain client and structured output added to the verifier.

**Consumer CI**: Median Gate run **292s (4.9 min)**, p90 313s. Trend
crept up to ~300s; consumer band stayed narrow at this point.

**Pain points**: Drift-issue volume spiked — ~75 consumer-drift +
integration-drift issues filed/closed during the phase, peaking Feb 7-8 with
10+/day. The drift detector loop fired constantly until the Phase 3 sync
hardening landed. Token rotation continued (#1105 Jan 26-27, #1246 Feb 4-6).

**What it couldn't do yet**: Treat Claude as a peer of Codex in the runner
contract (only optimizer used Claude); operate without ad-hoc consumer-drift
firefighting (Phase 3 sync hardening solved this); support per-agent label
routing in auto-pilot (Phase 3's `agent:auto`/`agent:claude` work).

**End-of-phase backlog**: 2 open issues, 2 open PRs — the tightest queue of any
end-of-phase except today.

---

## Phase 3 — Feb consolidation push (Feb 11 → Feb 28, 2026)

**Endpoint commit**: [`43f9454e`](https://github.com/stranske/Workflows/commit/43f9454e) — 413 commits in 2.5 weeks.

**What worked**: **Claude became a first-class agent** alongside Codex —
[`reusable-claude-run.yml`](../.github/workflows/reusable-claude-run.yml) shipped
on 2026-02-17 via #1534 (Phase 5A: `agent:auto`/`agent:claude` labels + widened
capability check), mirroring `reusable-codex-run.yml`. The Codex-specific belt
workflows were renamed agent-agnostic (`agents-belt-conveyor.yml`,
`agents-belt-dispatcher.yml`, `agents-belt-worker.yml`). The
`setup-api-client` composite action was introduced for vendored npm deps and
cross-repo auth, driving a wave of "fix: setup-api-client …" commits at phase
end. LangSmith tracing was wired end-to-end (#1542, #1551, #1558, #1579), with
[`maint-80-langsmith-metrics-dashboard.yml`](../.github/workflows/maint-80-langsmith-metrics-dashboard.yml)
surfacing telemetry. The consumer registry grew from 7 to 11 on 2026-02-28
(#1673: Counter_Risk + Pension-Data + Inv-Man-Intake + Ready).

**Agent footprint**: Codex 598, Claude jumps to 276 (5x from Phase 2),
Copilot 22.

**Consumer CI**: Median Gate run **412s (6.9 min)**, p90 850s (14.2 min). The
p90 jump was driven by Counter_Risk's first runs after onboarding (950–1028s
initial-onboarding LangChain installs) — a real cost the Phase 4 quiet would
later amortize.

**Pain points**: Race-condition-marker dedupe (#1670), CODEX_AUTH_JSON
47-hour warning (#1664), and the perpetual #405 (95% coverage) all stayed
open. The setup-api-client churn at end of phase was self-inflicted — the
introduction was correct, the rollout took several iterations.

**What it couldn't do yet**: Run unattended for weeks (Phase 4 would test
that — and surface the next set of gaps); resolve token rotation without
human intervention (the structural fix didn't land until Phase 5's #1734);
keep README's consumer count in sync with the manifest (still at "5 consumers"
in README despite 11 registered).

**End-of-phase backlog**: 4 open issues, 2 open PRs.

---

## Phase 4 — Production quiet (Mar 1 → Apr 11, 2026)

**Endpoint commit**: [`1b1de154`](https://github.com/stranske/Workflows/commit/1b1de154) — 45 commits in 6 weeks. **Zero commits between 2026-03-25 and 2026-04-11**.

**What worked**: This phase tested whether the system could run itself. Mostly
it could. The PR-health scanner subsystem landed early in the phase
(`reusable-agents-pr-health.yml` + #1681/#1683/#1684/#1686/#1687 — periodic
scanner, stalled-PR detection, configurable interval, opt-in Claude code
review for consumers via `maint-76-claude-code-review.yml` in the consumer
template). [CLAUDE.md](../CLAUDE.md) was rewritten — the strident
"NON-NEGOTIABLE" preamble of Phase 2 was replaced with a calm "Read These Docs
First" pointer to the canonical guides. Then the commits stopped.

**Agent footprint**: Codex 606, Claude 282, Copilot 22 — essentially flat
from Phase 3.

**Consumer CI**: Median Gate run **86s (1.4 min)**, p90 323s. **This number
is misleading** — only trip-planner had merged-PR volume during the quiet (8/8
runs ~75–90s), and Counter_Risk's two runs (310/353s) drag p90. Treat the 86s
median as a sampling artifact: it reflects what trip-planner ran at, not what
the system as a whole was doing.

**Pain points**: The quiet itself surfaced what the system *couldn't* do
unattended:
- **Token rotation gap** — #1710 ("🚨 CODEX_AUTH_JSON has expired - CI agents
  broken") opened on 2026-03-11 and stayed open for 34 days, covering nearly
  the entire Phase 4 silence. CI agents were broken for that whole window.
- **Sync staleness** — #1701 ("Consumer Repo Sync Stale 96+ Hours") opened
  2026-03-07 and stayed open until 2026-04-14. Same root cause: nobody around
  to triage.
- **Integration-Tests sync drift** — #1726 opened 2026-04-08 (the start of
  the 14-day stuck window I would later resolve in Phase 5).
- **PR backlog** — 12 open PRs at phase end (the largest of any phase
  endpoint), almost entirely stacked dependabot bumps and sync-review
  follow-ups waiting for a human to merge.

**What it couldn't do yet**: Stay healthy across multi-week silences. Token
rotation, sync freshness, and PR-merge throughput all required a human in the
loop. This was the brief that drove the Phase 5 work.

**End-of-phase backlog**: 7 open issues, 12 open PRs — the largest of any
phase endpoint.

---

## Phase 5 — Post-quiet re-engagement (Apr 12 → Apr 29, 2026, current)

**Endpoint commit**: [`e0d04b6c`](https://github.com/stranske/Workflows/commit/e0d04b6c) — 240 commits in 17 days; ~190 of them in the last 6 days.

**What worked**: A focused push to address the gaps Phase 4 exposed. The
biggest architectural additions:

- **Repo-review subsystem** — [`scripts/repo_review_evaluator.py`](../scripts/repo_review_evaluator.py)
  (+2,965 lines) plus `repo_review_issue_quality.py`, `upload_repo_review_issues.py`,
  and [`docs/ops/REPO_REVIEW_PROCESS.md`](ops/REPO_REVIEW_PROCESS.md).
  Reviews now require semantic content, evidence traces, process-chain
  checkpoints, duplicate detection, and freshness checks before issues are
  filed.
- **Sync/Dependabot campaign queue** — [`maint-82-sync-dependabot-campaign.yml`](../.github/workflows/maint-82-sync-dependabot-campaign.yml)
  + [`.github/scripts/sync_dependabot_campaign.js`](../.github/scripts/sync_dependabot_campaign.js)
  with claim-leases, source-review history, source-freshness tracking, and
  parse contracts so concurrent sweeps don't race or auto-close active campaigns.
- **Bot-comment auth coverage** — [`bot_comment_auth_coverage.js`](../.github/scripts/bot_comment_auth_coverage.js)
  (+853 lines) plus reusable auth-policy knob, with hard-block enforcement
  gated behind eligibility evidence.
- **Verifier + Codex CLI freshness monitoring** — [`health-76-codex-cli-freshness.yml`](../.github/workflows/health-76-codex-cli-freshness.yml)
  and `scripts/check_codex_cli_freshness.py`, plus a verifier ledger and
  legacy-model warning suppression.
- **Action-pin contract** — [`scripts/check_workflow_action_pins.py`](../scripts/check_workflow_action_pins.py)
  (PR #1925) enforcing SHA pins for third-party actions across the fleet.
- **Python 3.12 fleet pin** plus retirement of legacy `CODESPACES_WORKFLOWS`
  token paths in favor of canonical app-auth.
- **Durable-tracker convention** — this doc plus
  [`docs/ops/DURABLE_TRACKING_ISSUES.md`](ops/DURABLE_TRACKING_ISSUES.md) and
  the `tracker:durable` label, naming the auto-bot tracking issues so
  automations don't try to triage them.

**Agent footprint**: Codex 710 (+104 — biggest jump in any phase), Claude 282
(flat), Copilot 24. Codex was the focus of re-engagement work; Claude work
plateaued.

**Consumer CI**: Median Gate run **519s (8.7 min)**, p90 702s (11.7 min) —
the slowest median of any phase. Counter_Risk (556–708s) and Inv-Man-Intake
(677–717s) drove the increase; trip-planner stayed near 100s. Variance was
high (sd 266s). The slowness tracks the LangChain/LangSmith install cost on
heavier consumers; reducing that cost is an obvious next target.

**Pain points** (mostly addressed):
- The 14-day Integration-Tests sync drift (#1756) closed in Phase 5 via
  PR #1971's autofix-versions.env realignment.
- The Phase 4 token-rotation gap (#1710 → #1757 → #1773/#1774) led to
  PR #1734's Codex auto-persist refreshed-auth-bundle structural fix.
- README still cites a stale "5 first-party consumers" list and Feb-2026
  verifier metrics; the
  [`docs/INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) quick-setup section was
  realigned to the current event-hub defaults via PR #1926.

**What it can't do yet**: Reduce CI duration on heavy LangChain-using
consumers (the median has crept up across every phase except the artifactual
Phase 4 number). Self-rotate Codex tokens without secret-update access (#1976
remains a manual rotation).

**End-of-phase backlog**: 4 open issues, 0 open PRs at HEAD — the cleanest
queue of any phase endpoint despite the high commit volume. The 4 open issues
are 1 transient alert (#1976 token rotation) plus 3 durable trackers (#1796,
#1836, #1868) that are open by design.

---

## Cross-cutting trends

### Consumer Gate-CI duration trend

Sample method: per-phase, picked 2–4 most-active consumer repos, listed
merged PRs ≥5 LOC excluding chore-sync and dependabot, took the latest
successful Gate run's wall-clock duration.

| Phase | Median | p90 | n | Note |
|---|---:|---:|---:|---|
| 1. Bootstrap | 234s (3.9 min) | 257s | 12 | Tight band; consumer load light. |
| 2. v1.1.x | 292s (4.9 min) | 313s | 12 | Trend creeping up; band still narrow. |
| 3. Feb consolidate | 412s (6.9 min) | 850s | 13 | Counter_Risk onboarding LangChain installs drove p90. |
| 4. Production quiet | 86s (1.4 min) | 323s | 8 | **Sampling artifact** — only trip-planner was active. |
| 5. Re-engage | 519s (8.7 min) | 702s | 13 | Slowest median; Counter_Risk + Inv-Man-Intake LangChain weight. |

The trend: consumer CI has gotten slower as agent integrations matured
(LangChain, LangSmith, verifier follow-ups). Reducing install cost on heavy
consumers is the obvious next target.

### Consumer onboarding timeline

| Date | PRs | Repos added | Manifest size |
|---|---|---|---:|
| 2025-12-26 | #173, #202 | Travel-Plan-Permission, Template, trip-planner, Manager-Database | 4 |
| 2025-12-30 | #341 | Portable-Alpha-Extension-Model, Trend_Model_Project | 6 |
| 2026-01-04 | #500 | Collab-Admin | 7 |
| 2026-02-12 | #1485 | Counter_Risk | 8 |
| 2026-02-28 | #1673 | Pension-Data, Inv-Man-Intake, Ready | **11 (current)** |

### Agent registry growth

- **Codex** — present at the initial commit (2025-12-16); dominant from day
  one. `reusable-codex-run.yml` shipped in Phase 1.
- **Copilot** — referenced in Phase 1 only as auto-label and dedupe-comment
  guards; no dedicated runner. Mention count stable at 17–24 across all
  phases.
- **Claude** — first appears as scattered string references in Phase 1.
  First-class adoption in Phase 3:
  [`reusable-claude-run.yml`](../.github/workflows/reusable-claude-run.yml)
  ships 2026-02-17 (#1534), Sonnet 4.5 optimizer mid-Phase 2 (#1312),
  consumer-side `maint-76-claude-code-review.yml` opt-in at Phase 3/4 boundary
  (#1687). Workflow mentions plateau at 282 in Phase 5.

### Notable incidents

- **CODEX_AUTH_JSON token-rotation series** (10 incidents): #706 (Jan 9) → #930
  (Jan 17-18) → #1105 (Jan 26-27) → #1246 (Feb 4-6) → #1664 (Feb 26 → Mar 11)
  → **#1710 (Mar 11 → Apr 14, ~34-day gap covering the Phase 4 silence;
  CI agents broken)** → #1757 (Apr 14-20) → #1773/#1774 (Apr 20) → #1976
  (open). The Phase 4 incident is the canonical "token rotation gap"; PR #1734
  in Phase 5 added auto-persist of refreshed auth bundles as the structural
  fix.
- **Integration-Tests sync drift #1756** — opened 2026-04-14, closed
  2026-04-29 after 14 days. Root cause was `maint-69-sync-integration-repo.yml`
  silently skipping when `OWNER_PR_PAT`/`SERVICE_BOT_PAT` weren't available;
  see follow-up audit task spawned 2026-04-29.
- **Consumer Repo Sync Stale 96+ Hours** (#1701, #1764) — both Phase
  4-into-Phase 5 incidents reflecting the silence; resolved by Phase 5 sync
  hardening.
- **Drift-issue volume spike Feb 2026** — ~75 consumer-drift +
  integration-drift issues during Phase 2, peaking Feb 7-8 with 10+/day.
  Detector loop ran constantly until Phase 3 sync hardening (the `maint-68`
  Python-indentation fix #1598, "stage only manifest targets" #1596,
  header-aware diff later).
- **Phase 4 PR backlog** — 12 PRs open at 2026-04-11 (all stacked during the
  quiet); fully cleared during Phase 5 (0 open PRs at HEAD).

### Per-phase backlog snapshot (queue health)

| Phase end | Open issues | Open PRs | Note |
|---|---:|---:|---|
| 1 | 10 | 0 | All issues clustered in metrics-tracking + LangChain intake. |
| 2 | 2 | 2 | Tightest queue; drift loop firing but resolving same-day. |
| 3 | 4 | 2 | Race conditions + token rotation visible. |
| 4 | 7 | **12** | Quiet stacked the queue. |
| 5 | 4 | 0 | Cleanest queue; all 4 open issues either transient alert (#1976) or durable trackers. |

---

## Where the repo stands now

As of 2026-04-29 (HEAD `e0d04b6c`):

- **Workflow surface**: 101 workflow files in `.github/workflows/`,
  39 in `templates/consumer-repo/.github/workflows/`. Reusable contract is
  stable; consumer defaults are
  [`agents-issue-intake.yml`](../templates/consumer-repo/.github/workflows/agents-issue-intake.yml),
  [`agents-80-pr-event-hub.yml`](../templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml),
  [`agents-81-gate-followups.yml`](../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml),
  [`agents-verifier.yml`](../templates/consumer-repo/.github/workflows/agents-verifier.yml),
  [`autofix.yml`](../templates/consumer-repo/.github/workflows/autofix.yml),
  [`ci.yml`](../templates/consumer-repo/.github/workflows/ci.yml),
  and [`pr-00-gate.yml`](../templates/consumer-repo/.github/workflows/pr-00-gate.yml).
- **Consumer footprint**: 11 first-party consumers registered in
  `REGISTERED_CONSUMER_REPOS` (Travel-Plan-Permission, Template, trip-planner,
  Manager-Database, Portable-Alpha-Extension-Model, Trend_Model_Project,
  Collab-Admin, Counter_Risk, Pension-Data, Inv-Man-Intake, Ready) plus the
  Workflows-Integration-Tests harness.
- **Agent integrations**: Codex (canonical, dominant), Claude (first-class
  since Phase 3, optional code-review in consumers), Copilot (auto-label and
  dedupe-comment only).
- **Active surfaces with structural improvements from Phase 5**:
  repo-review pipeline with quality gates, sync/Dependabot campaign queue with
  claim-leases, bot-comment auth coverage with eligibility-gated hard-block,
  Codex CLI freshness monitoring, action-pin contract, Python-3.12 fleet pin,
  durable-tracker convention.
- **Open queue**: 4 open issues, 0 open PRs. Of the issues, 1 is a transient
  alert ([#1976](https://github.com/stranske/Workflows/issues/1976) — Codex
  token rotation, ~24h window) and 3 are durable auto-bot trackers
  ([#1796](https://github.com/stranske/Workflows/issues/1796),
  [#1836](https://github.com/stranske/Workflows/issues/1836),
  [#1868](https://github.com/stranske/Workflows/issues/1868)) — see
  [`docs/ops/DURABLE_TRACKING_ISSUES.md`](ops/DURABLE_TRACKING_ISSUES.md).
- **Known carry-over concerns**:
  - Median consumer Gate-CI duration has climbed each active phase (234s →
    292s → 412s → 519s for the heavier consumers). LangChain/LangSmith
    install cost is the main driver; this is the next obvious optimization
    target.
  - Token rotation still requires human secret-update access, even though
    auto-persist of refreshed bundles in PR #1734 reduced the failure mode.
  - README hasn't been refreshed since Phase 2; it still advertises the
    Feb 2026 verifier metrics and a 5-consumer footprint.
  - `maint-69-sync-integration-repo.yml` had three silent failures between
    2026-04-14 and 2026-04-20 because every step is gated on
    `token_available == 'true'` — a follow-up audit was spawned during the
    Phase 5 wrap to add alerting.

---

## See also

- [`CHANGELOG.md`](../CHANGELOG.md) — per-release records (the Unreleased
  section currently captures the Phase 5 work).
- [`README.md`](../README.md) — current capability advertisement (note: the
  consumer count and verifier metrics tables are stale as of HEAD).
- [`COMPATIBILITY.md`](../COMPATIBILITY.md) — versioning and deprecation
  policy adopted in Phase 2.
- [`docs/WORKFLOW_GUIDE.md`](WORKFLOW_GUIDE.md) — full inventory of current
  workflows and what each does.
- [`docs/ci/WORKFLOWS.md`](ci/WORKFLOWS.md) — workflow topology and active
  automation layout.
- [`docs/ops/DURABLE_TRACKING_ISSUES.md`](ops/DURABLE_TRACKING_ISSUES.md) —
  convention for the auto-bot tracking issues that should not be closed in
  routine triage.
