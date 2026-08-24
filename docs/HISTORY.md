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
| 5. Post-quiet re-engagement | 2026-04-12 → 2026-04-29 | 240 | 99 → 101 | 260 | — | Repo-review subsystem, sync/dependency campaign queue, action-pin contract, Python 3.12 fleet pin, durable-tracker convention |
| 6. Fleet review & systemic optimization | 2026-04-30 → 2026-05-07 (current) | 106 | 101 → 100 | 280 | — | 6-phase systematic review of all 101 workflows, 11 systemic fixes (state-fingerprint, event-eligibility, path-classifier, runner-lib, sync-tracker-state, issue-pr-context, verifier-config, reusable-ci-scope, artifact-cache, bot-comment-handler-fixtures, agents-guard split), Wave 0 deprecated-template cleanup, workflow-local follow-ons |

Counts cover the period through commit `969b8381` on 2026-05-07. Workflow file
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

## Phase 5 — Post-quiet re-engagement (Apr 12 → Apr 29, 2026)

**Endpoint commit**: [`e0d04b6c`](https://github.com/stranske/Workflows/commit/e0d04b6c) — 240 commits in 17 days; ~190 of them in the last 6 days.

**What worked**: A focused push to address the gaps Phase 4 exposed. The
biggest architectural additions:

- **Repo-review subsystem** — [`scripts/repo_review_evaluator.py`](../scripts/repo_review_evaluator.py)
  (+2,965 lines) plus `repo_review_issue_quality.py`, `upload_repo_review_issues.py`,
  and [`docs/ops/REPO_REVIEW_PROCESS.md`](ops/REPO_REVIEW_PROCESS.md).
  Reviews now require semantic content, evidence traces, process-chain
  checkpoints, duplicate detection, and freshness checks before issues are
  filed.
- **Sync/Dependency campaign queue** — [`maint-82-sync-dependency-campaign.yml`](../.github/workflows/maint-82-sync-dependency-campaign.yml)
  + [`.github/scripts/sync_dependency_campaign.js`](../.github/scripts/sync_dependency_campaign.js)
  with claim-leases, source-review history, source-freshness tracking, and
  parse contracts so concurrent sync/dependency-bot sweeps don't race or
  auto-close active campaigns.
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

## Phase 6 — Fleet review & systemic optimization (Apr 30 → May 7, 2026, current)

**Endpoint commit**: [`969b8381`](https://github.com/stranske/Workflows/commit/969b8381) — 106 commits in 8 days, with 50 commits on the May 6 merge day alone (Wave 0 + Wave 1-3 systemic fixes + workflow-local follow-ons all landing in one push).

**What worked**: The first systematic, evaluator-driven optimization
pass over the whole workflow fleet. Instead of incremental fixes, the
phase ran a 6-phase review rubric ([`docs/ops/WORKFLOW_REVIEW_RUBRIC.md`](ops/WORKFLOW_REVIEW_RUBRIC.md))
against every workflow file, scoring each on 4 dimensions (token cost,
CI time, code quality, automation gap), bucketing into 3 tiers (A: deep
review = 41 workflows, B: sanity skim, C: out-of-scope), and synthesizing
patterns across reviews into 11 shipped systemic fixes:

1. **state-fingerprint pattern** — [`scripts/state_fingerprint.py`](../scripts/state_fingerprint.py)
   with PR-comment + repo-variable storage backends, providing
   skip-when-state-unchanged for keepalive, autofix, and pr-meta loops.
   tiktoken estimator floors at `chars/4` so it can't be fooled by
   compressible inputs.
2. **event-eligibility composite action** —
   [`.github/actions/agent-event-eligibility/`](../.github/actions/agent-event-eligibility/)
   with expected-labels, expected-actions, JMESPath custom predicates,
   and enforce/warning modes for early-exit before agent compute.
3. **path-classifier** —
   [`.github/actions/path-classifier/`](../.github/actions/path-classifier/)
   plus [`.github/path-classification.yml`](../.github/path-classification.yml)
   for changed-paths → classification routing across gate workflows.
4. **runner-lib** — [`scripts/runner_lib/`](../scripts/runner_lib/)
   shared helpers (`assemble_prompt`, `parse_runner_output`,
   `should_dispatch`, `record_completion`) consolidating Codex/Claude
   dispatch out of inline workflow YAML.
5. **sync-tracker-state** —
   [`.github/scripts/sync_tracker_state/`](../.github/scripts/sync_tracker_state/)
   for find-or-create tracker, body update, and consumer-PR detection,
   with graceful 401/403 fallback so workflows still function without
   PAT/App token access.
6. **issue-pr-context builder** —
   [`scripts/langchain/issue_pr_context.py`](../scripts/langchain/issue_pr_context.py)
   with `build_issue_context`, `build_pr_context`, `reuse_formatted_body`.
7. **verifier-config consolidation** —
   [`scripts/langchain/verifier_config.py`](../scripts/langchain/verifier_config.py)
   (prompt budget constants, schema-repair policy, terminal-artifact
   gating).
8. **reusable-ci-scope** —
   [`scripts/reusable_ci_scope.py`](../scripts/reusable_ci_scope.py) for
   changed-input scenario selection in the reusable CI workflows.
9. **artifact-cache composite** —
   [`.github/actions/artifact-cache/`](../.github/actions/artifact-cache/)
   wrapping `actions/cache@v5` with run-window keys + producer-run
   discovery fallback.
10. **bot-comment-handler fixture coverage** — fixture-backed tests for
    [`reusable-bot-comment-handler.yml`](../.github/workflows/reusable-bot-comment-handler.yml)
    parsing edge cases (the original "extract an inline @agent parser"
    fix was re-scoped after Codex found no such parser existed; the
    fixtures cover the actual surface).
11. **Health 45 Agents Guard repo-aware split** —
    [`agents-guard.js`](../.github/scripts/agents-guard.js) refactored
    into `LEGACY_ALLOW_REMOVED_PATHS` + `CONSUMER_ONLY_ALLOW_REMOVED_PATHS`
    with `isConsumerOnlyRemovalAllowed()` so canonical and consumer
    repos enforce the right deletion policy. Resolved a chicken-and-egg
    where `pull_request_target` ran the base ref's guard against the
    head ref's deletions.

Adjacent to the systemic work: **Wave 0 cleanup** removed 6 deprecated
consumer-template workflows (`agents-autofix-loop.yml`,
`agents-bot-comment-handler.yml`, `agents-keepalive-loop.yml`,
`agents-pr-meta.yml`, `agents-verify-to-issue-v2.yml`,
`agents-verify-to-issue.yml`) past their 2026-02-15 deprecation deadline,
and 7 **workflow-local follow-ons** shipped as separate PRs (#2047
bot-comment-handler fixtures, #2051 auto-pilot transition extraction,
#2052 debug-event trigger tightening, #2053 agents-63 ChatGPT import
fixtures, #2054 maint-50 tool-version fixtures, #2055 reusable-10-ci-python
contract fixtures, #2056 health-75 inline-script extraction reducing
1,968 LOC → ~446 LOC across 9 modules + 5 fixtures).

The realization tracker
([`Workflows-fleet-review/realization-tracker.py`](https://github.com/stranske/Workflows-fleet-review)
in scratch) captured the post-merge T0 baseline and re-runs against it at
+7d / +30d / +60d milestones to surface realized-vs-estimated deltas.

**Agent footprint**: Codex 870 (+160, the largest single-phase jump in
any phase), Claude 389 (+107, first growth since Phase 3 — driven by
`reusable-claude-run` callsite expansion and the multi-agent repo-review
pipeline), Copilot 29.

**Consumer CI**: Median Gate run **203s (3.4 min)**, p90 ~470s, n=5
consumers × 10 recent successes each. The drop from Phase 5's 519s
median is the headline structural change — `path-classifier`,
`event-eligibility`, `artifact-cache`, and `reusable-ci-scope` collectively
short-circuit work that the heavier consumers (Counter_Risk, Pension-Data)
previously ran every gate. The 7-day window is short and the launch week
itself produced atypical activity, so the Workflows-fleet-review T+30
milestone re-read is the first comparison suitable for confident
realization claims.

**T+7 realization snapshot** (window: 2026-05-06 → 2026-05-13;
realization-tracker `--window-days 7`):

- **CI minutes realized: +49%** of synthesis-targeted savings already
  showing (4,212 of 8,528 min/mo across 21 workflows with quantified
  targets).
- **Per-workflow standouts**: `agents-pr-meta-v4.yml` 229% realized
  (7,035 → 600 min/mo), `agents-auto-pilot.yml` 94% (2,126 → 189),
  `agents-bot-comment-handler.yml` 124% (714 → 364), `agents-guard.yml`
  94% (582 → 328).
- **Skip-rate signal**: 26 workflows now emit fingerprint / eligibility /
  classifier markers. 5 show strong gating already
  (`agents-auto-pilot.yml` 100%, `agents-bot-comment-handler.yml` 100%,
  `autofix.yml` 78%, `agents-guard.yml` 70%, `agents-moderate-connector.yml`
  30%); the remaining 21 are wired and emitting markers but haven't yet
  exercised a skip in this window.
- **Incidents**: 0 priority:high incidents closed in the 7-day window
  (prior rate would have predicted ~2). One transient alert open
  (#2073 — recurring `CODEX_AUTH_JSON` expiry).
- **Aggregate token spend went UP** (31.3M → 50.9M/mo, +63%) — the
  targeted token reductions on specific workflows are real but swamped
  by the new multi-agent repo-review pipeline that landed mid-phase.
  The +30d re-read should disentangle these effects.
- **Workflows showing negative realization** (gates and self-tests
  running more than baseline) are likely contaminated by the May 4-7
  launch-week activity spike; the +30d window will normalize.

**Pain points**:
- Aggregate token use ticked up despite per-workflow reductions, because
  the multi-agent repo-review pipeline (commit `50002f59` on May 5)
  introduced a Codex/Claude round-1/round-2/body-writer flow that
  consumes tokens at a higher rate than the workflows it monitors. This
  is expected behavior — the pipeline is producing 6 new repo-review-
  approved issues per run (#2085-#2090) — but it confounds the
  token-savings story for the systemic fixes.
- 5 sync-review-comments-1836 PRs (#1985, #1994, #1995, #1996, #2009)
  remain open as closer-iteration debt from earlier rounds and are
  outside the Phase 6 scope.
- The realization tracker's T0 capture showed `skip_rate_signal=0`
  because of a sandbox-blocked `gh run view --log` cache write; the +7d
  re-run from a non-sandboxed shell surfaced 26 signaling workflows, so
  the gap was tooling-only.

**What it couldn't do yet**: Demonstrate per-fix realization with
statistical confidence at +7d — the launch-week activity contamination
makes several gate workflows appear to use more CI than baseline. The
+30d window is the earliest read suitable for the realization-vs-estimate
deltas to be confident. Token-spend confounding from the new repo-review
pipeline will also need disentangling at +30d.

**End-of-phase backlog**: 12 open issues, 7 open PRs. The composition
matters: of 12 issues, 6 are `repo-review-approved` outputs from the
working multi-agent pipeline (#2085-#2090 — the system *generating* its
own queue is the design goal), 3 are durable trackers
([#1796](https://github.com/stranske/Workflows/issues/1796),
[#1836](https://github.com/stranske/Workflows/issues/1836),
[#1868](https://github.com/stranske/Workflows/issues/1868)), 1 is the
recurring CODEX_AUTH alert (#2073), and 2 are automation alerts (#2079
integration-sync drift, #2082 CI tool updates). Of 7 open PRs, 5 are
closer-lane iterations on the same sync-review-1836 chain (#1985,
#1994, #1995, #1996, #2009); 2 are recent (#2048, #2050) follow-ons to
the runner-lib hardening. The "real" backlog — items requiring fresh
attention — is closer to 3 issues than to 12.

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
| 6. Fleet optimization | 203s (3.4 min) | ~470s | 50 | First measured drop. `path-classifier` + `event-eligibility` + `reusable-ci-scope` + `artifact-cache` short-circuiting work on heavy consumers. 7-day window — re-confirm at +30d. |

The trend: consumer CI got slower across Phases 1-5 as agent integrations
matured (LangChain, LangSmith, verifier follow-ups), then dropped sharply
in Phase 6 once the systematic fixes started short-circuiting ineligible
work. The Phase 6 number is from a short window and will be re-confirmed
at the +30d realization re-read.

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
  one. `reusable-codex-run.yml` shipped in Phase 1. Phase 6 saw the largest
  single-phase jump (+160 mentions, 710 → 870) as `runner-lib` callsites
  expanded.
- **Copilot** — referenced in Phase 1 only as auto-label and dedupe-comment
  guards; no dedicated runner. Mention count stable at 17–29 across all
  phases.
- **Claude** — first appears as scattered string references in Phase 1.
  First-class adoption in Phase 3:
  [`reusable-claude-run.yml`](../.github/workflows/reusable-claude-run.yml)
  ships 2026-02-17 (#1534), Sonnet 4.5 optimizer mid-Phase 2 (#1312),
  consumer-side `maint-76-claude-code-review.yml` opt-in at Phase 3/4
  boundary (#1687). Plateaued at 282 in Phase 5, then jumped to 389 in
  Phase 6 (+107) — driven by the multi-agent repo-review pipeline
  (Codex round-1 / Claude round-2 / body-writer) and broadened
  `reusable-claude-run` use.

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
- **Phase 6 launch-week activity spike** (May 4-7, 2026) — 91 PRs merged
  in a single 4-day window during the Wave 0/1/2/3 push, including 50
  commits on May 6 alone. This produced atypical gate / self-test
  traffic that contaminates the +7d realization read for several gate
  workflows (`pr-00-gate.yml`, `health-44`, `selftest-ci.yml`). The
  +30d window will normalize.
- **Repo-review pipeline as token sink** (started May 5, 2026) — the
  multi-agent repo-review pipeline (commit `50002f59` adding round-1 +
  round-2 + body-writer + coordinator) added a substantial new
  token-consumer at the same time as the systemic fixes tried to reduce
  fleet-wide token spend. Per-workflow token reductions are real but
  swamped in the aggregate; this is the design (pipeline-as-feature) and
  will be disentangled in the +30d realization analysis.

### Per-phase backlog snapshot (queue health)

| Phase end | Open issues | Open PRs | Note |
|---|---:|---:|---|
| 1 | 10 | 0 | All issues clustered in metrics-tracking + LangChain intake. |
| 2 | 2 | 2 | Tightest queue; drift loop firing but resolving same-day. |
| 3 | 4 | 2 | Race conditions + token rotation visible. |
| 4 | 7 | **12** | Quiet stacked the queue. |
| 5 | 4 | 0 | Cleanest queue; all 4 open issues either transient alert (#1976) or durable trackers. |
| 6 | 12 | 7 | Headline numbers up but composition matters: 6 of 12 issues are `repo-review-approved` pipeline outputs (#2085-#2090) — the design goal of the multi-agent pipeline — and 5 of 7 PRs are closer-iteration on the legacy sync-review-1836 chain. Net new attention needed ≈ 3 items. |

---

## Where the repo stands now

As of 2026-05-07 (HEAD `969b8381`):

- **Workflow surface**: 100 workflow files in `.github/workflows/`,
  32 in `templates/consumer-repo/.github/workflows/` (down from 39 at
  Phase 5 end after Wave 0 removed 6 deprecated consumer workflows past
  their 2026-02-15 deadline + 1 redundant canonical). Reusable contract
  is stable; consumer defaults are
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
  since Phase 3, expanded reach in Phase 6 via the multi-agent repo-review
  pipeline), Copilot (auto-label and dedupe-comment only).
- **Active surfaces with structural improvements from Phase 6**:
  - **state-fingerprint pattern** — `scripts/state_fingerprint.py` with
    PR-comment + repo-variable storage, gating keepalive/autofix/pr-meta
    loops on unchanged-state.
  - **event-eligibility composite** —
    `.github/actions/agent-event-eligibility/` with JMESPath custom
    predicates + enforce/warning modes; live skip-rate 30-100% on 5
    workflows.
  - **path-classifier composite** —
    `.github/actions/path-classifier/` routing gate work by changed-paths
    classification.
  - **runner-lib shared helpers** — `scripts/runner_lib/` consolidating
    Codex/Claude dispatch.
  - **sync-tracker-state helper** — `.github/scripts/sync_tracker_state/`
    with 401/403 graceful fallback.
  - **issue-pr-context with chars/4 token floor** —
    `scripts/langchain/issue_pr_context.py` honoring budgets on
    compressible inputs.
  - **verifier-config** — `scripts/langchain/verifier_config.py`
    centralizing prompt budgets + schema-repair policy.
  - **reusable-ci-scope** — `scripts/reusable_ci_scope.py` for changed-
    input scenario selection.
  - **artifact-cache composite** —
    `.github/actions/artifact-cache/` with run-window keys.
  - **Health 45 Agents Guard repo-aware split** — legacy vs
    consumer-only allow-removed-paths.
  - **Realization tracker** — re-runnable in
    `Workflows-fleet-review/realization-tracker.py` (scratch, not in
    repo) with `--compare A.json B.json` mode; T0 + T+7 snapshots
    captured, T+30 / T+60 milestones queued.
- **Active surfaces carried from Phase 5**: repo-review pipeline with
  quality gates, sync/dependency campaign queue with claim-leases,
  bot-comment auth coverage with eligibility-gated hard-block, Codex CLI
  freshness monitoring, action-pin contract, Python-3.12 fleet pin,
  durable-tracker convention. The repo-review pipeline expanded to a
  multi-agent format (round-1 + round-2 + body-writer + coordinator) on
  2026-05-05 (commit `50002f59`), producing the 6 `repo-review-approved`
  issues (#2085-#2090) in the current open queue.
- **Open queue**: 12 open issues, 7 open PRs — but most are designed-by-
  pipeline outputs or legacy chain debt, not net-new backlog. Of the 12
  issues, 6 are `repo-review-approved` pipeline outputs (#2085-#2090),
  3 are durable auto-bot trackers
  ([#1796](https://github.com/stranske/Workflows/issues/1796),
  [#1836](https://github.com/stranske/Workflows/issues/1836),
  [#1868](https://github.com/stranske/Workflows/issues/1868)), 1 is the
  recurring CODEX_AUTH_JSON expiry alert (#2073), and 2 are automation
  alerts (#2079 integration-sync drift, #2082 CI tool updates). Of the
  7 open PRs, 5 are closer-iteration on the legacy sync-review-1836
  chain (#1985, #1994, #1995, #1996, #2009) and 2 are recent runner-lib
  follow-ons (#2048, #2050). See
  [`docs/ops/DURABLE_TRACKING_ISSUES.md`](ops/DURABLE_TRACKING_ISSUES.md)
  for the durable-tracker convention.
- **Known carry-over concerns**:
  - Phase 6's +7d realization read shows +49% of targeted CI savings
    realized fleet-wide (4,212 of 8,528 min/mo). Several gate workflows
    show negative realization at +7d due to launch-week activity
    contamination — re-confirm at +30d (2026-06-05). The
    `Workflows-fleet-review/realization-tracker.py` script handles the
    re-run.
  - **Aggregate token spend is up** (31.3M → 50.9M/mo, +63%) despite
    per-workflow reductions, because the multi-agent repo-review
    pipeline is a substantial new consumer. The +30d analysis should
    separate the systemic-fix delta from the new-pipeline delta.
  - Token rotation still requires human secret-update access, even
    though auto-persist of refreshed bundles in PR #1734 reduced the
    failure mode. #2073 is the current iteration.
  - README hasn't been refreshed since Phase 2; it still advertises the
    Feb 2026 verifier metrics and a 5-consumer footprint. The
    `maint-66-monthly-audit.yml` quarterly README refresher exists but
    a manual sweep is overdue.
  - 21 of the 26 helper-wired workflows show `skip_rate=0` at +7d: the
    helpers are emitting markers but the eligibility / classifier
    predicates haven't yet rejected any events. Mostly expected (broad
    changes during launch week didn't narrow to skippable scope); the
    +30d read should show some of these activating as production traffic
    normalizes.

---

## See also

- [`CHANGELOG.md`](../CHANGELOG.md) — per-release records (the Unreleased
  section currently captures Phase 5 + Phase 6 work — no tag has been cut
  since `v1.1.2` in late January).
- [`docs/ops/WORKFLOW_REVIEW_RUBRIC.md`](ops/WORKFLOW_REVIEW_RUBRIC.md) —
  the 4-dimension / 3-tier / 6-phase rubric that drove Phase 6's
  systematic review.
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
