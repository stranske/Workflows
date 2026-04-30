# Workflow Fleet Review: Rubric and Process

This document defines the rubric, thresholds, phases, and Codex hand-off
conventions for the periodic deep review of every workflow in
`.github/workflows/`. It is the authoritative reference — if any phase
issue, review proposal, or implementation PR appears to disagree with this
document, this document wins until it is deliberately updated.

The review's purpose: **measurably reduce token usage, CI time, code-quality
debt, and automation-efficiency gaps across the workflow fleet, while
explicitly skipping workflows where no measurable improvement is available.**

The companion docs are:
- [`WORKFLOW_REVIEW_INVENTORY.md`](WORKFLOW_REVIEW_INVENTORY.md) — produced
  in Phase 1, kept fresh quarterly. The 30,000-ft view of every workflow.
- [`WORKFLOW_REVIEW_DECISIONS.md`](WORKFLOW_REVIEW_DECISIONS.md) — running log
  of changes made AND deliberate non-changes. Created in Phase 3.
- [`workflow-reviews/`](workflow-reviews/) — one review-doc per Tier A
  workflow, produced in Phase 3.

---

## The four dimensions

Every workflow is scored on four dimensions. Scores are **High / Medium / Low /
Not-applicable** based on measurable signals over the last 90 days.

| Dimension | What it measures | Primary signal | Source |
|---|---|---|---|
| **Token cost** | LLM token consumption per month | `tokens/run × runs/30d`, summed across LLM calls in the workflow | LangSmith dashboard, run logs, `aggregate_agent_metrics.py` |
| **CI time** | Wall-clock spent waiting on this workflow per month | `median_duration_s × runs/30d` | `gh run list` over last 30 days |
| **Code quality (agent-facing)** | How easy this workflow is for a coding agent (or human) to understand and safely modify | Associated script LOC, repeated patterns across workflows, count of incidents traced to this workflow, count of closed bug issues citing it | `git log --grep`, `wc -l` on referenced scripts, issue search |
| **Automation gap** | How often this workflow requires human intervention or causes stuck state | Frequency of human-required action (token rotation, manual re-runs), multi-day stuck windows traced here | Closed issue history, incident log in `HISTORY.md` |

A score of **N/A** is allowed and meaningful — many maintenance workflows have
no LLM calls (token cost N/A); many one-off helpers have no recurring CI
exposure. N/A on all four dimensions means the workflow is dormant and should
be checked for retirement separately.

---

## "Worth pursuing" thresholds

A change is **worth pursuing** if it crosses any one of these thresholds.
Below threshold = "skip, document why" — the rubric explicitly excludes
minor gains.

| Dimension | Threshold |
|---|---|
| Token cost | ≥10% reduction **and** the workflow consumes ≥1M tokens/month, **OR** the change addresses a recurring failure mode (≥3 occurrences in 90 days) |
| CI time | ≥30s/run × ≥40 runs/month, **OR** ≥1m/run × ≥10 runs/month — both yield ~10–20 min/month saved as the floor |
| Code quality | Only intervene if there is concrete evidence of harm: ≥2 incidents traced to this workflow OR ≥3 closed bug issues citing it OR associated script LOC > 500 with no test coverage |
| Automation gap | ≥1 human intervention/month required by this workflow, **OR** ≥1 multi-day stuck window in last 90 days traced here |

Thresholds are deliberately strict. They are the operationalization of "skip
minor gains." If a threshold is wrong for the fleet's context, this document
gets updated *first* — never adjust a threshold mid-review to justify a
particular workflow.

---

## Tier definitions

After scoring against the rubric, every workflow lands in one of three tiers.

| Tier | Definition | Treatment |
|---|---|---|
| **Tier A** | Clears at least one threshold above | Full deep-review proposal in Phase 3. One review-doc per workflow. Implementation PR (if approved) in Phase 6. |
| **Tier B** | Within 2× of any threshold but does not clear any | Batched sanity-skim in Phase 4 (5–10 workflows per Codex pass). Promotion to Tier A only if the skim surfaces a surprise. |
| **Tier C** | Well below all thresholds on all dimensions, no recent incidents | Not reviewed beyond the inventory row. Auto-promotes on a future quarterly inventory refresh if a threshold is later tripped (incident, slow run, token spike). |

Expected distribution from the current 101 workflows: ~15–25 Tier A, ~30–50
Tier B, the remainder Tier C. If Tier A balloons past ~30, the thresholds are
too loose; if Tier C balloons past ~70, too strict. Either signal triggers a
rubric-update review before the deep work proceeds.

---

## The six-phase process

**Read-only phases (1, 2, 3, 4) produce only inventory data and review docs.
No code changes to any workflow file land until Phase 6.** This is intentional:
Phase 5 synthesis must be able to reshape Phase 3 individual proposals into
systemic fixes before any per-workflow PR is created.

### Phase 1 — Instrument & inventory (read-only)

Produce [`WORKFLOW_REVIEW_INVENTORY.md`](WORKFLOW_REVIEW_INVENTORY.md): one
row per workflow file in `.github/workflows/` with run count, median + p90
duration, success rate, est. monthly token cost, associated script LOC,
recent failure modes, incident count, and any open/closed issues citing the
workflow.

**Codex hand-off**: one issue with `agent:codex` + `review:workflow-fleet`
labels. See "Codex hand-off conventions" below.

**Exit criterion**: every workflow file has a row, all data is from the last
90 days, the inventory passes the validation gate (script: `scripts/validate_workflow_review_inventory.py`, to be added in this phase).

### Phase 2 — Pareto bucketing (orchestration + judgment)

Apply the rubric to the inventory. Produce a tiered list:
`docs/ops/workflow-reviews/00-tier-list.md`. Each workflow gets `Tier: A|B|C`
with the dimension scores that drove the placement.

**Codex hand-off**: minimal — Codex can draft a first cut from the inventory
data, but the orchestrator (me) reviews every borderline placement and the
human (you) confirms the final list before Phase 3 starts.

**Exit criterion**: every workflow has a tier, distribution is within
expected ranges, you have signed off on the Tier A list explicitly.

### Phase 3 — Tier A proposals (read-only, no code changes)

For each Tier A workflow, produce a review document at
`docs/ops/workflow-reviews/<workflow-name>.md` using the template below.
**No changes to the workflow file itself — only the review doc.**

**Codex hand-off**: one issue per Tier A workflow with `agent:codex` +
`review:workflow-fleet` + `review:tier-a` labels. The issue body includes
the inventory row for the workflow, the rubric scores from Phase 2, and a
pointer to this rubric doc.

**Exit criterion**: every Tier A workflow has a complete review doc with
proposed changes, estimated impact per change, and an explicit "deliberately
not changing" section.

### Phase 4 — Tier B sanity skim (read-only)

For Tier B workflows, run a batched lightweight pass: each batch of 5–10
workflows gets a single review doc summarizing the skim verdict ("no action,
scored as expected" / "promote to Tier A" / "tighten one specific thing").

**Codex hand-off**: one issue per Tier B batch with `agent:codex` +
`review:workflow-fleet` + `review:tier-b` labels. Codex produces a single
batch review doc at `docs/ops/workflow-reviews/tier-b-batch-NN.md`.

**Exit criterion**: every Tier B workflow has been touched at least once;
any promotions to Tier A get added to the Phase 3 queue.

### Phase 5 — Cross-workflow synthesis (orchestration + judgment)

Read all Phase 3 review docs and Phase 4 batch summaries. Identify systemic
patterns: shared boilerplate that should become a reusable, repeated failure
modes that should get a fleet-wide guard, parallel structures that suggest a
common refactor.

Produce `docs/ops/workflow-reviews/00-synthesis.md` listing each systemic
pattern with the workflows it touches, the proposed systemic fix, and how
that fix interacts with the per-workflow proposals from Phase 3 (e.g.,
"this systemic fix supersedes the per-workflow change proposed in
`agents-foo.md` § X").

**Codex hand-off**: limited. Codex can draft the first synthesis pass by
clustering review-doc themes, but pattern recognition requires orchestrator
judgment. You sign off on which systemic fixes will be implemented.

**Exit criterion**: synthesis doc captures every cross-workflow pattern
worth acting on, every Phase 3 proposal is explicitly marked as "ship as
proposed," "supersede with systemic fix X," or "drop, redundant after
systemic fix X."

### Phase 6 — Implementation pass (PRs land)

Now — and only now — code changes happen. For each approved change (whether
from a Phase 3 proposal that survived synthesis, or a Phase 5 systemic fix):
file an implementation issue.

**Codex hand-off**: one issue per implementation with `agents:auto-pilot` (if
the change is fully scoped) or `agent:codex` (if you want to review before
merge). The issue body cites the source review doc + acceptance criteria
from the rubric.

**Exit criterion**: every approved change has a merged PR; every Phase 3
proposal is either implemented, superseded by a systemic fix, or marked
"deliberately not implementing — see decisions log."

---

## Per-workflow review template

Used in Phase 3. Codex fills this out for each Tier A workflow.

```markdown
# Workflow Review: <workflow file name>

- **File**: `.github/workflows/<name>.yml`
- **Tier**: A
- **Last 30d runs**: N | **Median**: Xs | **p90**: Ys | **Success rate**: Z%
- **Est. monthly token cost**: $W (M tokens)
- **Associated scripts**: `path/to/script.py` (LOC), `path/to/other.js` (LOC)

## Rubric scores

| Dimension | Score | Justification (data) |
|---|---|---|
| Token cost | H/M/L/N/A | Specific numbers from inventory |
| CI time | H/M/L/N/A | Specific numbers |
| Code quality | H/M/L/N/A | LOC, incident count, etc. |
| Automation gap | H/M/L/N/A | Human-intervention count |

## Recommended changes

For each: a one-line description, the rubric dimension it improves,
estimated impact, and the bar it clears.

1. **<change name>** — improves <dimension>. Estimated impact: <X tokens
   saved/run, Y seconds saved/run, Z incidents avoided>. Clears threshold:
   <which bar from the rubric>.
2. ...

## Deliberately not changing

For each: what was considered, why it isn't being changed.

- **<thing considered>** — reason: <below threshold | breaks contract X |
  superseded by Y | requires deferred work>.
- ...

## Suggested systemic patterns (input to Phase 5)

If this review noticed a pattern that might apply to other workflows, list
it here as a hint for synthesis.

- <pattern observation>
```

---

## Codex hand-off conventions

Each phase that delegates to Codex follows the same pattern:

1. **Issue body structure** (use this skeleton):

```markdown
## Source

This issue is part of the Workflow Fleet Review (see
[`docs/ops/WORKFLOW_REVIEW_RUBRIC.md`](../docs/ops/WORKFLOW_REVIEW_RUBRIC.md)),
**Phase <N>**.

## Why

<one sentence on what this phase produces and why it matters>

## Tasks

- [ ] <concrete task 1>
- [ ] <concrete task 2>

## Acceptance criteria

- [ ] Output committed to <exact path>.
- [ ] Output follows the template/schema in the rubric doc, section <X>.
- [ ] All numerical values cite source (run ID, query, file:line).
- [ ] Validation script `scripts/validate_<phase>_<artifact>.py` passes.
- [ ] No changes to any `.github/workflows/*.yml` file (Phase 1–5 only).

## Implementation notes

- Read `docs/ops/WORKFLOW_REVIEW_RUBRIC.md` first.
- Follow the per-workflow review template exactly; do not invent fields.
- If the rubric is ambiguous on something, comment on this issue rather
  than guessing — the orchestrator will clarify.

## Labels to apply

`agent:codex`, `review:workflow-fleet`, plus any phase label
(`review:tier-a`, `review:tier-b`, `review:phase-1`, etc.).
```

2. **Validation gates**: every artifact (inventory, review doc, synthesis
   doc) has a corresponding `scripts/validate_<thing>.py` script that
   enforces the schema. The acceptance criteria block requires the script
   to pass; this means a Codex PR can't merge without the artifact being
   well-formed. The validation scripts are added in Phase 1 (the inventory
   gate) and incrementally as each phase introduces a new artifact type.

3. **Escalation rules** — Codex should comment on the issue (not silently
   guess) when:
   - The rubric is ambiguous on a specific case
   - A workflow's data is missing or stale
   - A proposed change touches a contract documented in CLAUDE.md or
     COMPATIBILITY.md (these need orchestrator review even within Phase 6)
   - A Phase 3 proposal would touch >300 LOC across more than 3 files

4. **Quality bar via verifier** — every Phase 6 implementation PR gets
   `verify:evaluate` applied on merge. The verifier checks the diff against
   the acceptance criteria from the source review doc. Verdict feeds back
   into the decisions log.

---

## Deliverables and bookkeeping

| Artifact | Path | Created in | Maintained by |
|---|---|---|---|
| Rubric (this doc) | `docs/ops/WORKFLOW_REVIEW_RUBRIC.md` | One-time | Updated only on deliberate rubric review |
| Inventory | `docs/ops/WORKFLOW_REVIEW_INVENTORY.md` | Phase 1 | Refreshed quarterly via scheduled agent |
| Tier list | `docs/ops/workflow-reviews/00-tier-list.md` | Phase 2 | Refreshed when inventory refreshes |
| Per-workflow reviews | `docs/ops/workflow-reviews/<workflow>.md` | Phase 3 | Updated on next review cycle if workflow changes substantially |
| Tier B batches | `docs/ops/workflow-reviews/tier-b-batch-NN.md` | Phase 4 | Same |
| Synthesis | `docs/ops/workflow-reviews/00-synthesis.md` | Phase 5 | Same |
| Decisions log | `docs/ops/WORKFLOW_REVIEW_DECISIONS.md` | Phase 3 onward | Append-only |
| Validation scripts | `scripts/validate_workflow_review_*.py` | Phase 1 onward | Updated when an artifact schema changes |

The decisions log is append-only. Each entry is one workflow + one decision,
dated, with the rationale. Future-you in 6 months should be able to read it
and know why a workflow that "obviously needed work" in your eyes was
deliberately left alone.

Format:

```markdown
## YYYY-MM-DD — `agents-foo.yml`

**Decision**: ship per Phase 3 proposal | supersede with synthesis fix X
| deliberately not implementing

**Rationale**: <one paragraph>

**Source review**: [agents-foo.md](workflow-reviews/agents-foo.md)
```

---

## Cumulative impact tracking

After Phase 6 wraps, the orchestrator updates a section at the top of the
decisions log with cumulative numbers:

- Token cost reduction: X tokens/month → Y tokens/month
- CI time reduction (consumer Gate median): X seconds → Y seconds
- Incident-class reductions: which incident types are now structurally
  prevented
- Workflows reviewed: Tier A: N, Tier B: M, Tier C: P (untouched, by design)
- Workflows changed: K (~K/N rate)

Without this, future quarterly refreshes have no anchor for "did the last
review cycle actually help?" That number is the argument for doing the
next cycle.

---

## Roles

- **Orchestrator (Claude Code primary session)** — writes phase issue specs,
  reviews Codex output for rubric fidelity, runs Phase 2 first-cut bucketing,
  drafts Phase 5 synthesis, escalates judgment calls to the human
- **Executor (Codex via `agent:codex` and `agents:auto-pilot` lanes)** —
  data gathering for Phase 1, per-workflow proposal drafting for Phase 3,
  batch sanity skims for Phase 4, implementation PRs for Phase 6
- **Human (repo owner)** — confirms tier list at end of Phase 2, approves
  systemic fixes at end of Phase 5, final merge approval on Phase 6 PRs that
  touch CLAUDE.md / COMPATIBILITY.md contracts or that the verifier flags

---

## When to run this

The first full cycle is one-time and substantial — expect ~3–4 weeks of
elapsed calendar time even with parallelism. Subsequent cycles are
**quarterly inventory refreshes** that re-bucket against the rubric;
re-review only the workflows that move tiers or that were changed
substantially since the last review.

The quarterly inventory refresh can be a scheduled remote agent (same
pattern as the README refresh agent set up 2026-04-29). The deeper
re-review is human-triggered when the inventory delta warrants it.
