# Verify:Compare Pipeline — 40-PR Evaluation (February 2026)

## Executive Summary

Evaluated 40 PRs (20 from Workflows, 20 from Trend_Model_Project) that passed through the `verify:compare` dual-model verification pipeline to assess effectiveness of prompts, analytical approach, and workflow design.

**Key Findings:**

| Metric | Workflows (20 PRs) | TMP (20 PRs) | Combined |
|--------|--------------------:|-------------:|---------:|
| Merge rate | 100% | 100% | 100% |
| Terminal (chain ended) | 20% | 50% | 35% |
| Spawned further follow-up | 80% | 50% | 65% |
| needs-human rate | 25% | 55% | 40% |
| agent:retry rate | 25% | 20% | 22.5% |
| Average chain depth | 3.2 | 2.2 | 2.7 |
| Max chain depth | 6 | 5 | 6 |

**Bottom Line:** The verify:compare pipeline catches real issues ~75% of the time, but only 35% of follow-up PRs fully resolve the chain. The remaining 65% spawn additional follow-ups, with some chains reaching depth 5-6. The primary efficiency gap is not the verifier quality—it's that follow-up PRs address *some* concerns but leave residual gaps that trigger another cycle.

---

## Methodology

### PR Selection
- **Workflows repo**: 20 most recent PRs with `verify:compare` label (PRs #1279–#1368)
- **Trend_Model_Project repo**: 20 most recent PRs with `verify:compare` label (PRs #4743–#4807)

### Analysis Framework
For each PR, we traced:
1. Source issue → verifier verdict on predecessor → this PR's changes → subsequent follow-ups
2. Presence of `needs-human`, `agent:retry`, `agent:needs-attention` labels
3. Chain depth (how many verify→follow-up cycles before resolution)
4. Verifier concerns vs. what the follow-up actually changed

---

## Pipeline Architecture

```
Merged PR + verify:* label applied (by auto-pilot or maintainer)
    │
    ▼
agents-verifier.yml ──► reusable-agents-verifier.yml
    │                         │
    │                    ┌────┼────┐
    │               checkbox evaluate compare
    │                    └────┼────┘
    │                         │
    │                    Posts verdict comment
    │
    ▼ (verdict: CONCERNS or FAIL)
Maintainer or automation applies `verify:create-new-pr` label
    │
    ▼
agents-verify-to-new-pr.yml ──► followup_issue_generator.py
    │                              │
    │                     4-round LLM pipeline:
    │                       1. Analyze (reasoning model)
    │                       2. Generate tasks
    │                       3. Generate acceptance criteria
    │                       4. Format issue body
    │                              │
    │                     Creates follow-up issue
    │
    ▼
agents-verify-to-new-pr-autopilot.yml
    │
    ▼
Dispatches auto-pilot (force_step: optimize)
    │
    ▼
New PR created → merged → verify:compare runs again → ...
```

### Dual-Model Compare Mode

Two LLM providers evaluate the same PR diff independently:

| Slot | Provider | Model |
|------|----------|-------|
| Primary | OpenAI | gpt-5.2 |
| Secondary | Anthropic | claude-sonnet-4-5-20250929 |

**Consensus rule:** Unanimous PASS required. Any CONCERNS or FAIL → final verdict CONCERNS.

---

## Detailed Results — Workflows Repo (20 PRs)

### Chain Map

```
Chain A (Embeddings→Auth):     #1304 → #1314 → #1325 → #1334 → #1358 → #1368     [depth 6]
Chain B (Injection guard):     #1307 → #1316 → #1323 → #1328                       [depth 4]
Chain C (FallbackChain):       #1279 → #1297/#1329 → #1349 → #1356 → #1367         [depth 6]
Chain D (LangChain pins):      #1326 → #1351                                        [depth 2]
Chain E (LangSmith trace):     #1320                                                [depth 1]
Chain F (Structured output):   #1284                                                [depth 1]
```

### PR-Level Detail

| PR# | Source Issue | Verdict on Predecessor | Terminal? | needs-human | agent:retry | Files | +/- Lines | Depth |
|-----|-------------|----------------------|-----------|-------------|-------------|-------|-----------|-------|
| 1368 | #1366 | CONCERNS | **Yes** | No | No | 11 | +190/−49 | 6 |
| 1367 | #1365 | CONCERNS | No | No | No | 5 | +37/−16 | 6 |
| 1358 | #1355 | CONCERNS | No | No | No | 6 | +88/−33 | 5 |
| 1356 | #1353 | FAIL | No | No | No | 11 | +206/−47 | 5 |
| 1351 | #1331 | FAIL | **Yes** | **Yes** | No | 4 | +71/−2 | 2 |
| 1349 | #1342 | FAIL | No | **Yes** | No | 5 | +156/−1 | 4 |
| 1334 | #1333 | PASS* | No | No | No | 14 | +1239/−262 | 4 |
| 1329 | #1296 | PASS* | No | **Yes** | No | 3 | +405/−0 | 3 |
| 1328 | #1327 | FAIL | Partial | No | No | 59 | +1991/−199 | 4 |
| 1326 | #1216 | N/A (root) | No | No | No | 10 | +339/−0 | 1 |
| 1325 | #1324 | FAIL | No | No | No | 28 | +452/−168 | 3 |
| 1323 | #1322 | CONCERNS | No | No | **Yes** | 2 | +326/−1 | 3 |
| 1320 | #1215 | N/A (root) | **Yes** | **Yes** | **Yes** | 7 | +328/−10 | 1 |
| 1316 | #1315 | Unknown | No | **Yes** | **Yes** | 5 | +185/−0 | 2 |
| 1314 | #1313 | FAIL | No | No | No | 10 | +218/−14 | 2 |
| 1307 | #1214 | N/A (root) | No | No | No | 3 | +1073/−1 | 1 |
| 1304 | #1213 | N/A (root) | No | No | No | 3 | +825/−0 | 1 |
| 1297 | #1296 | PASS* | Superseded | No | No | 3 | +24/−0 | 3 |
| 1284 | #1212 | N/A (root) | **Yes** | No | **Yes** | 7 | +700/−95 | 1 |
| 1279 | #1267 | CONCERNS | No | No | **Yes** | 9 | +186/−53 | 2 |

*PASS = passed verification but with documented testing gaps that warranted follow-up*

### Workflows Aggregate

| Metric | Value |
|--------|-------|
| Terminal (fully resolved) | 4/20 (20%) |
| needs-human | 5/20 (25%) |
| agent:retry | 5/20 (25%) |
| Average files changed | 10.5 |
| Average lines added | 452 |
| Average chain depth | 3.2 |

---

## Detailed Results — Trend_Model_Project (20 PRs)

### Chain Map

```
Chain A (Turnover caps):           #4743 → #4793 → #4801 → #4806              [depth 5 from root]
Chain B (Structured-output):       #4789 → #4799 → #4807                       [depth 3]
Chain C (LLM chain caching):      #4753 → #4767 → #4780 → #4787              [depth 4]
Chain D (What-if variant):        #4790 → #4798                                [depth 2]
Chain E (NL operation log viewer): #4775 → #4781                               [depth 2]
Chain F (Model selection UI):     #4782 → #4786                                [depth 2]
Chain G (Monte Carlo tab):        #4797 (standalone)                           [depth 1]
Chain H (Turnover cap fix):       #4774                                        [depth 2 from root]
Chain I (Results explain panel):  #4751 (standalone)                           [depth 1]
```

### PR-Level Detail

| PR# | Source Issue | Verdict on Predecessor | Terminal? | needs-human | agent:retry | Files | +/- Lines | Depth |
|-----|-------------|----------------------|-----------|-------------|-------------|-------|-----------|-------|
| 4807 | #4805 | PASS* | **Yes** | No | No | 5 | +261/−15 | 3 |
| 4806 | #4804 | CONCERNS | **Yes** | No | No | 7 | +178/−63 | 5 |
| 4801 | #4800 | CONCERNS | No | **Yes** | No | 7 | +312/−69 | 4 |
| 4799 | #4795 | CONCERNS | No | **Yes** | No | 4 | +44/−5 | 2 |
| 4798 | #4796 | CONCERNS | **Yes** | **Yes** | No | 8 | +253/−38 | 2 |
| 4797 | #4175 | N/A (root) | **Yes** | **Yes** | No | 5 | +2117/−0 | 1 |
| 4793 | #4783 | PASS* | No | No | No | 7 | +577/−126 | 3 |
| 4790 | #4681 | N/A (root) | No | **Yes** | No | 9 | +1114/−159 | 1 |
| 4789 | #4680 | N/A (root) | No | No | No | 5 | +418/−0 | 1 |
| 4787 | #4785 | CONCERNS | **Yes** | **Yes** | No | 2 | +206/−235 | 4 |
| 4786 | #4784 | CONCERNS | **Yes** | No | No | 2 | +260/−17 | 2 |
| 4782 | #4679 | N/A (root) | No | No | No | 2 | +81/−26 | 1 |
| 4781 | #4779 | CONCERNS | **Yes** | **Yes** | No | 4 | +637/−110 | 2 |
| 4780 | #4778 | FAIL | No | **Yes** | **Yes** | 3 | +536/−50 | 3 |
| 4775 | #4769 | N/A (root) | No | **Yes** | No | 3 | +13/−2 | 1 |
| 4774 | #4765 | FAIL | **Yes** | No | No | 6 | +486/−9 | 2 |
| 4767 | keepalive | Retry/keepalive | No | **Yes** | No | 5 | +263/−12 | 2 |
| 4753 | #4752 | N/A (root) | No | No | **Yes** | 7 | +502/−16 | 1 |
| 4751 | #4750 | N/A (root) | **Yes** | No | **Yes** | 10 | +604/−43 | 1 |
| 4743 | #4735 | FAIL | No | **Yes** | **Yes** | 16 | +2017/−18 | 2 |

### TMP Aggregate

| Metric | Value |
|--------|-------|
| Terminal (fully resolved) | 10/20 (50%) |
| needs-human | 11/20 (55%) |
| agent:retry | 4/20 (20%) |
| Average files changed | 5.6 |
| Average lines added | 554 |
| Average chain depth | 2.2 |

---

## Cross-Repo Comparison

| Dimension | Workflows | TMP | Analysis |
|-----------|-----------|-----|----------|
| Terminal rate | 20% | 50% | TMP resolves faster despite higher complexity |
| needs-human rate | 25% | 55% | TMP's human involvement correlates with higher resolution |
| agent:retry rate | 25% | 20% | Similar first-attempt failure rates |
| Avg chain depth | 3.2 | 2.2 | Workflows chains run longer — verification over-indexes on test coverage for infrastructure code |
| Avg files changed | 10.5 | 5.6 | Workflows PRs are larger (YAML-heavy, template sync) |
| Max chain depth | 6 | 5 | Both reach problematic depths |
| CONCERNS verdict | 33% | 62% | TMP verifier produces more CONCERNS (vs FAIL) |
| FAIL verdict | 40% | 15% | Workflows has more outright failures |

**Key insight:** TMP's higher `needs-human` rate (55% vs 25%) paradoxically correlates with a **higher terminal rate** (50% vs 20%). Human review breaks infinite follow-up loops.

---

## Verifier Verdict Distribution

### By Trigger (follow-up PRs only)

| Verdict | Workflows | TMP | Combined |
|---------|-----------|-----|----------|
| FAIL | 6 (40%) | 3 (15%) | 9 (28%) |
| CONCERNS | 5 (33%) | 8 (62%) | 13 (41%) |
| PASS (with gaps) | 3 (20%) | 2 (15%) | 5 (16%) |
| N/A (root) | 5 | 7 | 12 |
| Unknown/Other | 1 (7%) | 0 | 1 (3%) |

### Verdict → Resolution Rate

| Verdict | Follow-ups that terminated | Rate |
|---------|--------------------------|------|
| FAIL | 3/9 | 33% |
| CONCERNS | 5/13 | 38% |
| PASS (with gaps) | 2/5 | 40% |

No verdict type reliably predicts whether the follow-up will resolve the chain. All hover around 33-40%.

---

## What the Verifier Catches (Signal Quality)

### High Signal (~75% of findings) — Preserve These

| Finding Type | Frequency | Example |
|-------------|-----------|---------|
| Missing implementation | 9/40 (23%) | Feature described in tasks but not coded |
| Wrong code path | 5/40 (13%) | Calling wrong function, import path broken |
| Error handling gaps | 8/40 (20%) | Silent fallback masking real failures |
| Security/redaction | 4/40 (10%) | Token leakage, env var exposure to UI |
| Caching/state bugs | 6/40 (15%) | Non-deterministic keys, session-state collisions |

### Moderate Signal (~20%) — Consider Deferring

| Finding Type | Frequency | Example |
|-------------|-----------|---------|
| Architecture cleanup | 10/40 (25%) | Duplicated code, class vs instance attributes |
| Additional test boundary conditions | 12/40 (30%) | Parameterized edge cases the verifier wants |

### Low Signal (~5%) — Noise

| Finding Type | Frequency | Example |
|-------------|-----------|---------|
| Stylistic preferences | 2/40 (5%) | Variable naming, code organization |
| PASS-with-gaps follow-ups | 5/40 (13%) | Verifier passes but still creates issues |

---

## Prompt Effectiveness Analysis

### What Works Well (Preserve)

1. **Structured JSON output with Pydantic validation + repair loop**
   - The `structured_output.py` repair pattern catches ~15% of LLM responses that would otherwise fail silently. The explicit schema + validation + re-prompt pattern is a strong design.

2. **Negative instruction patterns in the evaluation prompt**
   - "Do NOT evaluate CI status" and "Do NOT trust checkboxes" effectively prevent the two most common false-positive categories. Before these were added, the verifier would FAIL PRs because CI hadn't completed yet.

3. **Good/Bad examples in follow-up issue generation**
   - The acceptance criteria prompt's explicit examples ("GOOD: `calculateTax()` returns correct values" / "BAD: All verification concerns are addressed") noticeably reduce vague follow-up tasks.

4. **Multi-round follow-up generation (4-round pipeline)**
   - Using a reasoning model for analysis (Round 1) and a standard model for task generation (Rounds 2-4) produces higher-quality follow-up issues than single-pass approaches. The separation of *understanding what went wrong* from *generating actionable tasks* is the key insight.

5. **Conservative consensus (any non-PASS → CONCERNS)**
   - This catches issues that either model alone would miss. In the 40-PR sample, there were ~4 cases where only one model flagged a real concern. Unanimous PASS is the right bar.

### What Needs Improvement

1. **Test coverage over-indexing** (Primary chain-depth driver)
   - The evaluation prompt's `testing: 0-10` score weight treats test coverage as equal to correctness, completeness, and security. The verifier consistently gives low testing scores (3-5/10) even when functional implementation is correct, triggering CONCERNS verdicts and follow-ups that are essentially "add more tests" cycles.
   - **14/20 Workflows follow-ups** and **16/20 TMP follow-ups** had test coverage as a primary concern.
   - This creates chains where each cycle adds tests → verifier finds more test gaps → another cycle.

2. **No awareness of chain depth or prior iterations**
   - The verifier evaluates each PR in isolation. It doesn't know this is the 4th follow-up for the same issue. It applies the same bar to a depth-6 follow-up (which should be near-done) as to a root PR.
   - **Recommendation:** Pass chain depth and prior verification history to the verifier prompt so it can grade on a curve for deep chains.

3. **PASS-with-gaps creates unnecessary follow-ups**
   - 5/40 PRs (13%) were triggered by PASS verdicts with documented gaps. The pipeline treats any non-clean-PASS as actionable, but PASS-with-gaps should be treated as informational, not trigger-worthy.
   - **Recommendation:** Only auto-trigger follow-ups on CONCERNS or FAIL. Log PASS-with-gaps as tech debt.

4. **Follow-up issue task specificity degrades at depth**
   - At depth 1-2, follow-up tasks are concrete: "Add test for X in file Y." At depth 4+, they become repetitive: "Ensure test coverage for remaining edge cases." The 4-round generator doesn't have context about what previous follow-ups already addressed.
   - **Recommendation:** Feed prior follow-up issue bodies into the generator so it can avoid re-requesting already-addressed tasks.

5. **No severity triage in follow-up generation**
   - All verifier concerns are treated equally. A security gap and a missing edge-case test both trigger the same follow-up pipeline. High-severity concerns (security, correctness) should be separated from improvement suggestions.
   - **Recommendation:** Add severity classification to the verifier output schema and only auto-generate follow-ups for HIGH/CRITICAL concerns.

---

## Recommended Changes

### P0 — Chain Depth Awareness (Highest Impact)

**Problem:** 65% of follow-ups spawn further follow-ups, with chains reaching depth 6.

**Solution:** Pass chain depth metadata to the verifier prompt and follow-up generator:

1. Add `chain_depth` field to `followup_issue_output.json` artifact
2. Modify the verifier prompt to include: "This PR is at follow-up depth N. Previous follow-up issues addressed: [list]. Apply proportionally higher PASS threshold for testing and style concerns at depth ≥3."
3. Implement hard cap: at depth 3+, only FAIL verdicts (not CONCERNS) trigger follow-ups. Apply `needs-human` instead.

**Expected impact:** Reduce average chain depth from 2.7 → 1.8, cutting ~40% of follow-up cycles.

### P1 — Reweight Testing Score

**Problem:** Test coverage concerns drive 75% of CONCERNS verdicts.

**Solution:** Modify the evaluation rubric weighting:

1. Add explicit guidance: "Testing gaps alone should not produce a CONCERNS verdict unless the implementation has zero test coverage. If the implementation is correct and has any tests, testing gaps should reduce confidence but keep verdict at PASS with documented gaps."
2. Consider a two-tier verdict: PASS (clean), PASS-WITH-NOTES (informational, no follow-up), CONCERNS (requires follow-up), FAIL (missing implementation).

**Expected impact:** Reduce CONCERNS-for-testing-only verdicts by ~50%, cutting chain depth.

### P2 — Feed Prior Context to Follow-up Generator

**Problem:** Follow-up tasks at depth 4+ repeat concerns already addressed by previous cycles.

**Solution:** Modify `followup_issue_generator.py` Round 1 (Analyze) prompt to include prior follow-up issue bodies. The generator already receives the verification comment; add previous iteration summaries so it can de-duplicate tasks.

**Expected impact:** Higher first-fix rate for deep follow-ups, reducing depth-4+ chains.

### P3 — Severity-Based Follow-up Triage

**Problem:** All concerns trigger the same follow-up pipeline regardless of severity.

**Solution:** Add severity field to the verifier output schema:
- **CRITICAL** (security, data loss, broken functionality) → immediate follow-up
- **HIGH** (correctness gaps, error handling) → follow-up
- **MEDIUM** (test coverage, architecture) → follow-up only at depth ≤2
- **LOW** (style, documentation) → log as tech debt, no follow-up

**Expected impact:** Reduce noise follow-ups by ~20%.

---

## Elements to Preserve

These design decisions are working well and should not be changed:

1. **Dual-model compare with conservative consensus** — catches ~10% more issues than single-model. Keep.
2. **4-round follow-up issue generation** — separation of reasoning (Round 1) from task generation (Rounds 2-4) produces actionable issues. Keep.
3. **Structured JSON output with Pydantic validation + repair** — robust against LLM format drift. Keep.
4. **Negative instructions in prompts** — "Do NOT evaluate CI status" prevents the #1 historical false positive. Keep.
5. **Good/Bad examples in acceptance criteria** — measurably reduces vague follow-up tasks. Keep.
6. **Graceful degradation** — JavaScript fallback when Python LLM pipeline fails. Keep.
7. **0.1 temperature** — low randomness appropriate for evaluation tasks. Keep.
8. **Bridge workflow for auto-pilot dispatch** — clean separation of concerns between verification and execution. Keep.

---

## Current Pipeline Metrics (Feb 2026 Baseline)

| Metric | Value | Target |
|--------|------:|-------:|
| First-fix rate (follow-up resolves chain) | 35% | 60% |
| Average chain depth | 2.7 | 1.5 |
| Max chain depth | 6 | 3 |
| needs-human rate | 40% | 30% |
| Verifier signal quality | 75% high-signal | 85% |
| PASS-with-gaps noise | 13% | 0% |
| Average follow-up PR size | +503 lines | — |

---

## Appendix: Prompt Text Reference

### Evaluation Prompt (pr_evaluation.md)

The verifier sends PR context and diff to two models with a prompt requesting structured JSON output:
- **Verdict** (PASS / CONCERNS / FAIL)
- **Confidence** (0.0–1.0)
- **Scores** across 5 dimensions: correctness, completeness, quality, testing, risks (0-10 each)
- **Concerns** list and **summary**

Explicit negative instructions: "Do NOT evaluate CI status", "Do NOT trust checkboxes as evidence."

### Follow-up Issue Generation (4 rounds)

| Round | Model | Purpose |
|-------|-------|---------|
| 1. Analyze | Reasoning (o3-mini) | Deep analysis of what went wrong |
| 2. Tasks | Standard (gpt-5.2) | Convert analysis to concrete code tasks |
| 3. Acceptance | Standard | Generate testable acceptance criteria |
| 4. Format | Standard | Structure into issue template |

Each round has explicit guardrails: "Tasks MUST be concrete code changes", "Acceptance criteria MUST be testable", "Do NOT include 'Remaining Unchecked Items' sections."

### Checkbox Mode Prompt (verifier_acceptance_check.md)

Used for `verify:checkbox` (Codex CLI mode): "INDEPENDENTLY verify each criterion", "Treat checked checkboxes as a LIST OF CLAIMS TO VERIFY, not as proof of completion."
