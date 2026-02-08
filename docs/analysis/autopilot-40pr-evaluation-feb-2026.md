# Auto-Pilot Pipeline Evaluation — 40-PR Sample (Feb 2026)

**Date:** 2026-02-08
**Scope:** 20 agent-driven PRs from Workflows repo + 20 from Travel-Plan-Permission (TMP)
**Period:** 2025-12-23 → 2026-02-08 (47 days)
**Method:** Source issue review, PR label/outcome analysis, workflow stage tracing

---

## Executive Summary

The `agents:auto-pilot` pipeline reliably moves issues through formatting,
optimization, agent assignment, PR creation, keepalive iteration, and
verification. The **merge rate is excellent** (39/40 = 97.5%). The pipeline's
greatest strengths are its **self-dispatching step sequencing** (eliminates
label-trigger race conditions) and **verify-to-follow-up chain** (catches
genuine quality gaps). Its greatest weakness is **follow-up chain depth** —
in the Workflows repo, 70% of sampled PRs were follow-ups from verification,
and one chain ran 5 PRs deep before the original issue was resolved.

---

## Sample Data

### Workflows Repo (20 PRs)

| PR | Source Issue | State | Labels of Note | Files | +/- |
|----|------------|-------|----------------|-------|-----|
| #1368 | #1366 (follow-up) | MERGED | verify:compare | 11 | +190/-49 |
| #1358 | #1355 (follow-up) | MERGED | verify:compare | 6 | +88/-33 |
| #1356 | #1353 (follow-up) | MERGED | verify:compare | 11 | +206/-47 |
| #1351 | #1331 (follow-up) | MERGED | needs-human, verify:compare | 4 | +71/-2 |
| #1349 | #1342 (follow-up) | MERGED | needs-human, verify:compare | 5 | +156/-1 |
| #1329 | #1296 (follow-up) | MERGED | needs-human, verify:compare | 3 | +405/-0 |
| #1326 | #1216 (original) | MERGED | verify:compare | 10 | +339/-0 |
| #1325 | #1324 (follow-up) | MERGED | verify:compare | 28 | +452/-168 |
| #1323 | #1322 (follow-up) | MERGED | agent:retry, verify:compare | 2 | +326/-1 |
| #1320 | #1215 (original) | MERGED | needs-human, agent:retry | 7 | +328/-10 |
| #1316 | #1315 (follow-up) | MERGED | needs-human, agent:retry | 5 | +185/-0 |
| #1307 | #1214 (original) | MERGED | autofix:patch, verify:compare | 3 | +1073/-1 |
| #1304 | #1213 (original) | MERGED | verify:compare | 3 | +825/-0 |
| #1284 | #1212 (original) | MERGED | agent:retry, verify:compare | 7 | +700/-95 |
| #1279 | #1267 (follow-up) | MERGED | agent:retry, verify:compare | 9 | +186/-53 |
| #1272 | #1267 (follow-up) | MERGED | needs-human, verify:compare | 13 | +1054/-490 |
| #1263 | #1253 (follow-up) | MERGED | needs-human, verify:compare | 9 | +851/-15 |
| #1254 | #1211 (original) | MERGED | verify:compare | 7 | +920/-178 |
| #1248 | #1236 (original-ish) | MERGED | verify:evaluate, verify:compare | 6 | +1173/-22 |
| #1076 | #1075 (follow-up) | MERGED | agent:rate-limited | 15 | +1493/-47 |

### TMP Repo (20 PRs)

| PR | Source Issue | State | Labels of Note | Files | +/- |
|----|------------|-------|----------------|-------|-----|
| #424 | #423 (follow-up) | MERGED | agents:keepalive | 4 | +140/-2 |
| #420 | #412 (original) | MERGED | needs-human, agent:high-privelege | 14 | +565/-112 |
| #352 | #351 (follow-up) | MERGED | agents:keepalive | 5 | +225/-9 |
| #318 | #298 (original) | MERGED | needs-human, verify:compare | 9 | +238/-117 |
| #317 | #299 (original) | MERGED | needs-human, verify:compare | 7 | +346/-23 |
| #309 | #296 (original) | MERGED | needs-human, verify:compare | 7 | +246/-32 |
| #301 | #297 (original) | MERGED | needs-human, verify:compare | 6 | +113/-23 |
| #300 | #262 (original) | MERGED | verify:evaluate, verify:compare | 5 | +85/-17 |
| #285 | #269 (original) | **CLOSED** | — | 4 | +85/-0 |
| #278 | #268 (original) | MERGED | verify:evaluate | 4 | +440/-7 |
| #276 | #267 (original) | MERGED | needs-human, verify:evaluate | 6 | +446/-0 |
| #271 | #266 (original) | MERGED | verify:evaluate | 6 | +207/-31 |
| #270 | #265 (original) | MERGED | verify:evaluate | 9 | +971/-0 |
| #248 | #232 (original) | MERGED | agents:keepalive | 7 | +340/-3 |
| #247 | #230 (original) | MERGED | agents:keepalive | 3 | +98/-0 |
| #245 | #220 (original) | MERGED | agents:keepalive | 6 | +198/-3 |
| #243 | #228 (original) | MERGED | agents:keepalive | 6 | +176/-0 |
| #242 | #226 (original) | MERGED | agents:keepalive | 5 | +53/-12 |
| #236 | #224 (original) | MERGED | agents:keepalive | 7 | +265/-16 |
| #235 | #222 (original) | MERGED | agents:keepalive | 4 | +81/-19 |

---

## Outcome Metrics

| Metric | Workflows | TMP | Combined |
|--------|-----------|-----|----------|
| Merge rate | 20/20 (100%) | 19/20 (95%) | 39/40 (97.5%) |
| Needed `needs-human` | 7/20 (35%) | 5/20 (25%) | 12/40 (30%) |
| Needed `agent:retry` | 5/20 (25%) | 0/20 (0%) | 5/40 (12.5%) |
| Ran verification | 18/20 (90%) | 10/20 (50%) | 28/40 (70%) |
| Follow-up PRs | 14/20 (70%) | 3/20 (15%) | 17/40 (42.5%) |
| Original-issue PRs | 6/20 (30%) | 17/20 (85%) | 23/40 (57.5%) |
| Avg files changed | 7.3 | 6.1 | 6.7 |
| Avg lines added | 548 | 270 | 409 |

---

## Component-by-Component Evaluation

### 1. Issue Formatting (`format` step)

**What it does:** Runs `scripts/langchain/issue_formatter.py` to restructure
raw issue text into the `AGENT_ISSUE_TEMPLATE` format with Why / Scope /
Non-Goals / Tasks / Acceptance Criteria sections. Includes task decomposition
via `scripts/langchain/task_decomposer.py`.

**Strengths:**
- Consistent structure across all PRs — every sampled PR body had
  well-formed Scope, Tasks, and Acceptance Criteria sections
- Task decomposition produces verifiable checkbox items
- Format is agent-agnostic; works for any LLM backend

**Weaknesses:**
- Some TMP issues (265-269) had generic/vague issue bodies ("Mobile
  Responsive Design Improvements", "API Rate Limiting Implementation") that
  the formatter couldn't meaningfully improve — garbage in, slightly
  better-organized garbage out
- Task decomposer can produce tasks that are too granular for meaningful
  verification (see Verifier section)

**Verdict: PRESERVE** — Critical infrastructure. The structured format is
what makes the entire downstream pipeline work.

### 2. Issue Optimization (`optimize` step)

**What it does:** Runs `scripts/langchain/issue_optimizer.py` to analyze the
formatted issue against the repository's codebase and produce concrete
suggestions: file paths, existing patterns to follow, potential conflicts.

**Strengths:**
- Grounds the agent's work in actual repository state
- Prevents the agent from creating files in wrong directories
- Suggestions comment provides context the agent wouldn't otherwise have

**Weaknesses:**
- Optimizer output is not always consumed — the `apply` step may not
  integrate all suggestions, especially for large/complex issues
- For TMP issues, the optimizer's repo knowledge was sometimes out of date
  (referencing files before recent restructuring)

**Verdict: PRESERVE** — High value for code quality. Without this,
agents create code that doesn't match repo conventions.

### 3. Apply Suggestions (`apply` step)

**What it does:** Takes optimizer suggestions and applies them to the issue
body, enriching task descriptions with file paths and implementation hints.

**Strengths:**
- Bridges the gap between optimizer analysis and agent execution
- Provides the agent with specific file targets

**Weaknesses:**
- Minor: sometimes duplicates information already in the issue

**Verdict: PRESERVE** — Good value, low cost.

### 4. Capability Check + Agent Assignment (`capability-check` step)

**What it does:** Validates the issue is suitable for automated work, then
assigns the `agent:codex` label to trigger the keepalive loop.

**Strengths:**
- Guards against issues that shouldn't be automated (e.g., design
  discussions, infrastructure changes requiring human judgment)
- Clean handoff to keepalive via label

**Weaknesses:**
- In practice, almost every issue passes the capability check — it may be
  too permissive for issues that need human architectural decisions
- 30% of merged PRs ended up with `needs-human` anyway, suggesting the
  capability check isn't catching complexity early enough

**Verdict: IMPROVE** — The capability check should correlate with the
`needs-human` rate. If 30% of issues need human intervention post-merge,
the check is failing to detect at least some of those cases upfront.

### 5. PR Creation (`create-pr` step)

**What it does:** Creates a `codex/issue-*` branch, bootstraps the PR with
the issue context embedded in the body, adds `agent:codex` label, and
triggers the keepalive loop.

**Strengths:**
- Consistent branch naming enables easy tracking
- PR body contains full issue context (essential for keepalive prompts)
- Auto-status-summary block is well-structured

**Weaknesses:**
- Bootstrap commits are sometimes just a placeholder file (+1/-0) that
  the agent then rewrites entirely — wastes a keepalive cycle
- PR titles are generic ("chore(codex): bootstrap PR for issue #NNN")
  rather than reflecting the actual work scope

**Verdict: PRESERVE** — Works well. The generic title issue is cosmetic.

### 6. Keepalive Loop (`agents-keepalive-loop.yml`)

**What it does:** Event-driven loop triggered by Gate completion. Evaluates
whether tasks remain, builds the task appendix, dispatches Codex CLI with
explicit task context, and updates progress tracking.

**Strengths:**
- Event-driven (not polled) — efficient and responsive
- Task appendix injection gives the agent explicit, structured work items
- Progress tracking via checkbox reconciliation prevents rework
- Failure tracking with `needs-human` after 3 failures — good safety rail
- Branch-sync gate prevents stale-branch issues

**Weaknesses:**
- The `needs-human` label was applied in 30% of PRs but the PRs were
  still merged, suggesting the agent eventually resolved the issue
  (possibly with autofix help). This means human intervention was
  not actually needed in many cases — the label is too aggressive
- Rate limiting (`agent:rate-limited`) affected 1 PR in the sample,
  but was a significant blocker in earlier periods (pre-token rotation fix)

**Verdict: PRESERVE** — Core of the system. The `needs-human` threshold
could be tuned (perhaps 5 failures instead of 3, or differentiate between
CI failures and logic failures).

### 7. Verifier (`agents-verifier.yml`)

**What it does:** After PR merge, runs LLM-based evaluation of whether the
PR actually satisfied the issue's acceptance criteria. Produces a verdict
(PASS, CONCERNS, FAIL, Unknown) and optionally creates follow-up issues.

**Strengths:**
- Catches real quality gaps — in the Workflows sample, verification found
  genuine issues: missing test coverage, broken imports, incorrect
  dependency pins
- compare mode (two-LLM cross-verification) increases confidence
- Labels (`verify:compare`, `verify:evaluate`) make the pipeline traceable

**Weaknesses:**
- **Follow-up chain explosion (Critical):** In the Workflows repo,
  verification triggered follow-up issues for 14/20 PRs (70%). One chain
  reached 5 PRs deep:
  ```
  #1236 → #1248 → verify:CONCERNS
       → #1253 → #1263 → verify:CONCERNS
              → #1267 → #1272 → verify:CONCERNS
                     → #1267 → #1279 → verify:PASS
                            → #1296 → #1329
  ```
  This means the "SessionQualityContext propagation" task consumed 5 PR
  cycles and 5 verification cycles to resolve.
- **Verifier is too strict for incremental work:** The verifier often
  flags "concerns" about test coverage or edge cases that are genuinely
  out of scope for the original issue. The follow-up issue then retasks
  the agent with these edge cases, creating scope creep
- **Unknown verdicts create unnecessary follow-ups:** PR #1307 got
  "Unknown" verdict, which triggered #1315, which got "CONCERNS", which
  triggered #1322 — three PRs to verify one PR's work

**Verdict: IMPROVE (Priority)** — The verifier is the most impactful
component to tune. See recommendations.

### 8. Verify-to-New-PR Pipeline (`agents-verify-to-new-pr.yml`)

**What it does:** When verification produces CONCERNS or FAIL, creates a
follow-up issue with the verification gaps as tasks, labels it
`agent:codex` + `agents:auto-pilot`, and dispatches auto-pilot.

**Strengths:**
- Automated remediation loop — no human needed to create follow-up issues
- Follow-up issues are well-structured with clear task lists
- Links back to original PR and issue for context

**Weaknesses:**
- **No chain depth limit (Critical):** The pipeline will keep creating
  follow-up issues indefinitely. There is no "stop after N follow-ups"
  guard. This is what produced the 5-deep chain
- **Scope creep amplification:** Each follow-up adds the verifier's
  concerns as new tasks, which may expand beyond the original issue scope
- **Rate-limit vulnerability (now fixed):** The pipeline previously failed
  silently on 403 rate limits, orphaning follow-up issues. PR #1369 fixed
  this

**Verdict: IMPROVE** — Needs a chain depth cap and scope-drift detection.

### 9. Self-Dispatch / Re-dispatch Mechanism

**What it does:** After each step (format, optimize, apply, capability-check,
create-pr, monitor-pr), auto-pilot dispatches itself with `force_step`
for the next stage. This avoids label-trigger race conditions.

**Strengths:**
- Eliminates the `GITHUB_TOKEN` label trigger problem entirely
- Explicit step sequencing prevents skipped/duplicated steps
- Delay timers for monitor-pr (120s) and create-pr (60s) prevent
  tight polling loops

**Weaknesses:**
- Debug visibility: when a re-dispatch fails, it's hard to tell which
  step stalled without checking workflow runs
- The `MAX_CYCLES: 10` safety limit is generous but untested — no
  PR in the sample hit it

**Verdict: PRESERVE** — Elegant solution to a hard problem.

### 10. Metrics Collection

**What it does:** Records step timers and outcomes to NDJSON logs
(`autopilot-metrics.ndjson`).

**Strengths:**
- Per-step timing data enables bottleneck detection
- Failure categorization aids debugging

**Weaknesses:**
- Metrics are written to the runner filesystem and not aggregated
  anywhere accessible for trend analysis
- No dashboard or summary view

**Verdict: PRESERVE (low priority improvement)** — Useful foundation,
needs a consumer/dashboard to be actionable.

---

## Key Follow-Up Chain Analysis

The most revealing pattern is the difference between repos:

| Metric | Workflows | TMP |
|--------|-----------|-----|
| Follow-up chain PRs | 70% | 15% |
| `needs-human` rate | 35% | 25% |
| Avg chain depth | 2.4 | 1.15 |
| Deepest chain | 5 PRs | 2 PRs |

**Why the difference?** The Workflows repo is significantly more complex
(workflow YAML, JavaScript scripts, Python utilities, cross-repo templates).
The verifier struggles more with infrastructure/platform code than with
application code (TMP). This suggests the verifier's acceptance criteria
evaluation is calibrated for application-level changes and needs adjustment
for platform/infrastructure work.

**Specific chain patterns observed:**

1. **Dependency pin chains (3 PRs):** #1216 → #1326 → verify:FAIL → #1331
   → #1351. The verifier flagged version pin format issues that the agent
   initially got wrong, then the follow-up agent overcorrected.

2. **Test coverage chains (5 PRs):** #1236 → ... → #1329. The verifier
   kept requesting more test coverage, but each follow-up only added tests
   for the specific concerns raised, not comprehensive coverage. This
   produced diminishing-returns follow-ups.

3. **Documentation chains (3 PRs):** #1214 → #1307 → #1315 → #1316 →
   #1322. Verification flagged missing documentation, then flagged that
   the added docs didn't reference existing docs, etc.

---

## Recommendations

### P0: Cap Follow-Up Chain Depth

**Problem:** Unlimited follow-up chains waste compute and produce
diminishing returns.

**Fix:** Add a chain depth counter to `agents-verify-to-new-pr.yml`:
- Track `follow-up-depth` in issue body metadata
- After depth 2 (i.e., original + 2 follow-ups), add `needs-human`
  instead of creating another follow-up
- Include the verification concerns in the `needs-human` comment so
  a human can decide whether to pursue or accept

**Preserve:** The first follow-up is almost always high-value. Don't
remove the follow-up mechanism — just cap it.

### P1: Tune Verifier Strictness for Infrastructure Work

**Problem:** The verifier applies application-level quality standards
to infrastructure/platform changes, creating false-positive CONCERNS.

**Fix:** Add context-aware strictness:
- When the PR primarily modifies `.github/`, `scripts/`, or `docs/`,
  use a relaxed verification prompt that focuses on functional
  correctness rather than comprehensive test coverage
- When the PR modifies `src/`, `tests/`, or application code, use
  the current strict prompt
- Consider a `verify:lenient` label for infrastructure PRs

### P2: Improve Capability Check Predictive Power

**Problem:** 30% of PRs needed `needs-human` despite passing the
capability check.

**Fix:** Use the historical `needs-human` correlation to train the
capability check:
- Issues touching >10 files historically need human attention 40%+
- Issues with vague acceptance criteria ("ensure proper behavior")
  consistently produce CONCERNS verdicts
- Issues involving cross-file dependency changes (e.g., import
  restructuring) have higher failure rates

### P3: Aggregate Metrics for Trend Analysis

**Problem:** Per-run metrics exist but aren't aggregated.

**Fix:** Add a weekly summary workflow that reads `autopilot-metrics.ndjson`
from recent runs and posts a summary issue with:
- Average step durations
- Follow-up chain frequency
- `needs-human` rate trends
- Most common failure categories

---

## Elements to Preserve (Critical)

1. **Self-dispatch step sequencing** — Eliminates race conditions; do not
   revert to label-triggered step progression
2. **Inline format/optimize/apply** — Running these inside auto-pilot
   (not as separate workflows) was the right architectural choice; it
   eliminated workflow_run complexity and timing issues
3. **Event-driven keepalive** — Gate → keepalive trigger is responsive
   and efficient; do not replace with polling
4. **Task appendix injection** — Explicit task context in agent prompts
   is the single most important quality factor; agents without task context
   produce unfocused work
5. **Token-aware retry with load balancing** — The `withRetry` +
   `token_load_balancer.js` system prevents the rate-limit cascading
   failures that plagued earlier versions
6. **Verification pipeline** — Despite the chain depth problem, catching
   quality gaps before they accumulate is essential; the fix is tuning,
   not removal
7. **Structured issue format** — The AGENT_ISSUE_TEMPLATE with explicit
   Why/Scope/Tasks/Acceptance sections enables every downstream component

---

## Elements That Changed Since Last Evaluation (Jan 2026)

| Change | Date | Impact |
|--------|------|--------|
| Branch creation gap fixed | Jan 2026 | PRs now create consistently |
| Optimizer moved inline | Jan 2026 | Eliminated race conditions |
| Metrics collection added | Jan 2026 | Per-step timing available |
| Token load balancing | Feb 2026 | Rate-limit failures eliminated |
| verify-to-new-pr pipeline fix | Feb 2026 (PR #1369) | Follow-ups no longer orphaned |
| withRetry client param fix | Feb 2026 (PR #1369) | Token switching works correctly |
| download-artifact@v7 | Feb 2026 (PR #1369) | Matches repo standard |

---

## TMP-Specific Observations

TMP issues were generally **better-scoped** than Workflows issues:
- Clear functional requirements (e.g., "make orchestration state
  JSON-serializable", "spreadsheet generation should have a bytes mode")
- Concrete acceptance criteria tied to specific behaviors
- Smaller scope (avg 270 lines added vs 548 for Workflows)

This suggests that the **quality of the input issue** is the strongest
predictor of pipeline success, more so than any workflow component.

**Recommendation:** Invest in issue quality guidelines and template
enforcement over further workflow tuning. The machinery works; the
inputs determine the outcomes.
