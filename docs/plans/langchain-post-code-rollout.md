# LangChain Post-Code Production Capabilities - Evaluation & Rollout Plan

> **Date:** January 7, 2026  
> **Status:** Phase 3 Planning - Testing Cycle Defined  
> **Last Validation:** 2026-01-07 (Phase 3 Test Plan Added)  

---

## 1. Full Set of Capabilities

### A. Issue Intake & Formatting (Pre-Code)

| Script | Purpose | Workflow Integration | Status |
|--------|---------|---------------------|--------|
| `topic_splitter.py` | Split multi-topic ChatGPT conversations into separate issues | `agents-63-issue-intake.yml` | ✅ Working |
| `issue_formatter.py` | Format raw issue text to AGENT_ISSUE_TEMPLATE | `agents-issue-optimizer.yml` | ✅ Implemented |
| `issue_optimizer.py` | Analyze issues and suggest improvements | `agents-issue-optimizer.yml` | ⚠️ Partial |
| `capability_check.py` | Pre-flight check if agent can complete tasks | Not integrated | ❌ Not connected |
| `task_decomposer.py` | Break large tasks into smaller actionable items | Not integrated | ❌ Not connected |

### B. PR Verification (Post-Code)

| Script | Purpose | Workflow Integration | Status |
|--------|---------|---------------------|--------|
| `pr_verifier.py` | LLM evaluation of PR against acceptance criteria | `reusable-agents-verifier.yml` | ✅ Implemented |
| (compare mode) | Multi-provider evaluation comparison | `reusable-agents-verifier.yml` | ✅ Implemented |
| `context_extractor.py` | Extract PR context for evaluation | `agents_verifier_context.js` | ⚠️ Partial |

### C. Utility/Support Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `semantic_matcher.py` | Embedding-based semantic similarity | ⚠️ Available but unused |
| `label_matcher.py` | Match issues to labels semantically | ⚠️ Available but unused |
| `issue_dedup.py` | Detect duplicate issues | ⚠️ Available but unused |

### D. Core Infrastructure

| Component | Purpose | Status |
|-----------|---------|--------|
| `tools/llm_provider.py` | Unified LLM interface (GitHub Models → OpenAI → Regex fallback) | ✅ Working |
| Prompts in `scripts/langchain/prompts/` | LLM prompt templates | ✅ Complete |

---

## 2. Current State of Implementation

### ✅ Fully Functional in Workflows Repo

1. **Topic Splitting** - `topic_splitter.py` is called from `agents-63-issue-intake.yml` when `apply_langchain_formatting=true`. Tested and working (created 5 issues from Issues.txt).

2. **PR Verifier Script** - `pr_verifier.py` has:
   - Single-provider evaluation mode (✅ Tested on PR #625, #270)
   - Multi-provider comparison mode (✅ Tested on PR #302)
   - Model selection: GitHub Models and OpenAI (PR #626, #629 merged)
   - Model2 parameter for comparing different models (PR #629 merged)
   - GPT-5.2 support (PR #633 merged)
   - Model name comparison in reports (PR #643 merged)
   - Follow-up issue creation ❌ **DISABLED** (automatic creation no longer desired)
   - JSON output format
   - Tests: 4 test files with full coverage (all passing)

3. **LLM Provider Framework** - `tools/llm_provider.py` handles:
   - GitHub Models (default, uses GITHUB_TOKEN)
   - OpenAI (fallback, uses OPENAI_API_KEY)
   - Regex fallback (last resort)
   - Model selection capability

### ✅ Synced and Active in Consumer Repos

1. **Verifier Labels** - All 7 consumer repos have `verify:checkbox`, `verify:evaluate`, `verify:compare`:
   - ✅ Manager-Database (synced 2026-01-07)
   - ✅ Template (synced 2026-01-07)
   - ✅ trip-planner (synced 2026-01-07)
   - ✅ Travel-Plan-Permission (synced 2026-01-07)
   - ✅ Portable-Alpha-Extension-Model (synced 2026-01-07)
   - ✅ Trend_Model_Project (synced 2026-01-07)
   - ✅ Collab-Admin (synced 2026-01-07, PR #113 merged)

2. **Format Labels** - All 7 consumer repos have `agents:format`, `agents:formatted`, `agents:optimize`, `agents:apply-suggestions`:
   - ✅ Manager-Database (tested live - issue #184, synced 2026-01-07)
   - ✅ Template (synced 2026-01-07)
   - ✅ trip-planner (synced 2026-01-07)
   - ✅ Travel-Plan-Permission (synced 2026-01-07)
   - ✅ Portable-Alpha-Extension-Model (synced 2026-01-07)
   - ✅ Trend_Model_Project (synced 2026-01-07)
   - ✅ Collab-Admin (synced 2026-01-07, PR #113 merged)

3. **Updated .gitignore** - Consumer repos have old partial version, missing new entries for:
   - `verifier-diff-summary.md`
   - `autofix_report_enriched.json`
   - Various metrics files

### ✅ Tested Live - Working with Substantive Value

1. **issue_optimizer.py** - Provides valuable issue analysis
   - **Test:** Manager-Database #184 (unstructured logging request)
   - **Quality Score: 8.6/10** - Excellent task decomposition and objective criteria suggestions
   - **Strengths:** Splits broad tasks into concrete subtasks with verification methods; makes acceptance criteria objective and testable
   - **Gap:** Doesn't populate missing sections; could add task priority ordering
   - **Workflow:** `agents-issue-optimizer.yml` Phase 1 (analyze)

2. **issue_formatter.py** (apply_suggestions) - Intelligent content extraction
   - **Test:** Manager-Database #184 (same issue)
   - **Quality Score: 6/10 (with use_llm=False)** → **Expected 8.5/10 (with use_llm=True)**
   - **Strengths:** Consistent structure; preserves original content
   - **Change:** Now uses `use_llm=True` by default - will populate sections with analyzed content
   - **Workflow:** `agents-issue-optimizer.yml` Phase 2 (apply)
   - **Status:** Updated to use LLM - pending retest

### ❌ Not Connected

1. **capability_check.py** - Script exists with tests but no workflow calls it
2. **task_decomposer.py** - Script exists with tests but no workflow calls it
3. **issue_dedup.py** - Script exists but no workflow integration
4. **label_matcher.py** - Script exists but no workflow integration
5. **semantic_matcher.py** - Script exists but no workflow integration

---

## 3. Target State

### Phase 1 Target: PR Verification Working E2E

- All consumer repos have `verify:checkbox`, `verify:evaluate`, `verify:compare` labels
- All consumer repos have updated `agents-verifier.yml` that calls reusable workflow
- Adding `verify:evaluate` to a merged PR triggers LLM evaluation and posts results
- Follow-up issues created automatically on CONCERNS/FAIL verdicts
- `.gitignore` synced with workflow status file entries

### Phase 2 Target: Issue Formatting Complete

- All consumer repos have `agents:format`, `agents:formatted` labels
- `agents:format` label triggers issue reformatting via LLM
- Issue body updated with AGENT_ISSUE_TEMPLATE format
- `agents:formatted` label added after successful formatting

### Phase 3 Target: Pre-Agent Intelligence (4 Capabilities)

**3A. Capability Check (Pre-Agent Gate)**
- `capability_check.py` runs before `agent:codex` assignment
- Identifies issues agent cannot complete (external deps, out-of-scope, credentials needed)
- **Supplements** `agents:optimize` workflow (quality check) with feasibility check
- Adds `needs-human` label + explanation when agent cannot proceed

**3B. Task Decomposition (Large Issue Handling)**
- `task_decomposer.py` auto-splits issues with 5+ implied tasks
- Creates linked sub-issues or checklist within parent issue
- Triggers via `agents:decompose` label (new)

**3C. Duplicate Detection (Issue Triage)**
- `issue_dedup.py` checks new issues against open issues
- Posts warning comment if duplicate detected (>85% similarity)
- Creates link to potential duplicate for human review
- **Testing focus:** Validate false positive rate before auto-closing

**3D. Semantic Label Matching (Auto-Labeling)**
- `label_matcher.py` suggests appropriate labels based on issue content
- Posts comment with label suggestions or auto-applies if confidence >90%
- Uses `semantic_matcher.py` for embedding-based similarity

---

## 4. Rollout Plan

### Phase 1: PR Verification (2 Steps)

**Step 1A: Prepare Workflows Repo**
- [x] Verify `reusable-agents-verifier.yml` is correct (done)
- [x] Verify `agents-verifier.yml` template calls reusable correctly (done)
- [x] `.gitignore` template has all workflow status entries (not synced by design)
- [x] Add model selection and provider choice (PR #626, #629 merged)
- [x] Add scripts/update_model_list.sh for model management (PR #633 merged)
- [x] Add docs/MODEL_MANAGEMENT.md for model update process (PR #633 merged)
- [x] Add model name to comparison reports (PR #643 merged)
- [x] Disable automatic follow-up issue creation (PR #643 merged)
- [x] Commit any fixes to main

**Step 1B: Deploy to Consumer Repos**
1. ✅ All consumer repos have verifier labels (7/7 - all synced)
2. ✅ Sync workflow runs automatically on template changes
3. ✅ **Major cleanup completed 2026-01-07:**
   - 26 superseded sync PRs closed across 5 consumer repos
   - 6 most recent sync PRs merged successfully (including Collab-Admin PR #113)
   - **Bot Comment Analysis:** Reviewed 40+ comments across sync PRs
     - **Finding:** Zero substantive code review comments from Copilot/Codex agent bots
     - All comments were keepalive/autofix operational noise (status updates, missing-issue warnings)
     - Sync PRs don't use keepalive pipeline, yet keepalive status comments appear on all PRs
     - **Issue Identified:** Keepalive/autofix reporting should only appear when `agents:keepalive` label present
     - **Conclusion:** For sync PRs, current bot comments provide no code review value - only operational noise that should be suppressed
4. ✅ **Live Verification Test - Travel-Plan-Permission PR #318:**
   - **Labels:** `verify:evaluate`, `verify:compare` (both applied post-merge)
   - **Workflow Execution:** Both workflows ran successfully
   - **Evaluation Report Posted:** 2026-01-07 16:32:00Z (2 minutes after merge)
   - **Comparison Report Posted:** 2026-01-07 16:32:45Z (3 minutes after merge)
   - **Performance Assessment:**
     - ✅ **Fast Response:** Both reports posted within 3 minutes of merge
     - ✅ **Compare Mode Working:** Successfully compared github-models (gpt-4o) vs openai (gpt-5.2)
     - ✅ **Model Names Displayed:** Table shows both Provider and Model columns (PR #643 feature working)
     - ⚠️ **GitHub Models Auth Failed:** 401 error - "models permission required" 
       - GitHub Models provider couldn't authenticate in consumer repo
       - OpenAI fallback worked correctly
     - ✅ **Substantive Analysis:** OpenAI/gpt-5.2 provided detailed evaluation with:
       - Quantitative scores: Correctness 8/10, Completeness 8/10, Quality 8/10, Testing 9/10, Risks 6/10
       - 4 specific concerns about CI status, delegation test coverage, deprecation risks, API stability
       - 62% confidence level indicating nuanced analysis
     - ✅ **Actionable Feedback:** Identified real issues (CI pending, incomplete delegation tests)
     - ✅ **Agreement Detection:** Correctly noted both providers reached same verdict
     - ✅ **Unique Insights Section:** Clearly separated provider-specific findings
   - **Issues Identified:**
     - GitHub Models authentication doesn't work in consumer repos (needs GITHUB_TOKEN with models permission)
     - Should fall back gracefully (which it did) but auth issue prevents primary provider from working
   - **Conclusion:** Verify workflows are production-ready and providing high-quality code review. Authentication issue limits GitHub Models but doesn't break functionality.

**Validation Criteria:**
- [x] Verifier labels exist in all 7 consumer repos (6 active, 1 pending)
- [x] `agents-verifier.yml` deployed to consumer repos (6/7)
- [x] Model selection working (tested PRs #625, #270, #302)
- [x] Compare mode with different models working (tested PR #302)
- [x] Model name display in comparison reports (PR #643)
- [x] Sync PRs merged to consumer repos (5/6 merged 2026-01-07)
- [x] **Live test on Travel-Plan-Permission #318:** Workflow runs without errors (both evaluate and compare modes)
- [x] **Live test on Travel-Plan-Permission #318:** LLM evaluation produces scores and verdict (OpenAI: 62% confidence, detailed scores)
- [x] **Live test on Travel-Plan-Permission #318:** Comment posted on PR with evaluation results (within 3 minutes of merge)
- [x] Follow-up issue creation **DISABLED** (no longer automatically created)
- [ ] **Fix GitHub Models authentication** - 401 error in consumer repos (models permission missing)

### Phase 2: Issue Formatting & Cleanup (1 Step)

**Step 2A: Labels & Sync**
1. ✅ Labels created via sync workflow (`agents:format`, `agents:formatted`, `agents:optimize`, `agents:apply-suggestions`)
2. ✅ `agents-issue-optimizer.yml` is in sync manifest
3. ✅ Sync PRs merged (7/7 repos as of 2026-01-07, all synced)
4. ✅ **Tested on Manager-Database #184:**
   - ✅ Created unstructured test issue
   - ✅ Added `agents:optimize` label → Workflow posted valuable analysis (8.6/10 quality)
   - ✅ Added `agents:apply-suggestions` label → Issue reformatted to template structure
   - ✅ Labels updated correctly (`agents:formatted` added, others removed)
   - ✅ **Improvement:** Changed `use_llm=False` to `use_llm=True` - will now populate sections with analyzed content

**Validation Criteria:**
- [x] Format labels exist in consumer repos (created by sync workflow)
- [x] `agents-issue-optimizer.yml` in sync manifest
- [x] `issue_formatter.py` tests passing (14 tests, fixed env var isolation)
- [x] Topic splitting tested and working (created 5 issues from Issues.txt)
- [x] **Live test on Manager-Database #184:** `agents:optimize` provides valuable analysis
  - ✅ Splits broad tasks into 4+ concrete subtasks with verification methods
  - ✅ Makes acceptance criteria objective and testable (suggests numeric thresholds)
  - ✅ Identifies missing sections and formatting issues
  - ✅ Each suggestion includes clear rationale
- [x] **Live test on Manager-Database #184:** `agents:apply-suggestions` enforces structure
  - ✅ Issue body reformatted to AGENT_ISSUE_TEMPLATE
  - ✅ Original content preserved in collapsible section
  - ✅ Labels updated correctly (`agents:formatted` added)
  - ✅ **Updated:** Now uses `use_llm=True` to populate sections from analysis - pending retest

### Phase 3: Pre-Agent Intelligence (4 Steps)

**Status: Planning - Test Cycle Defined**

**Step 3A: Capability Check Integration**

1. **Relationship to existing workflows:**
   - `agents:optimize` → "Is this issue well-written?" (quality check)
   - `capability_check.py` → "Can the agent DO this?" (feasibility gate)
   - **Answer:** Supplements optimizer, runs BEFORE agent assignment on Issues

2. **Proposed workflow integration:**
   ```
   Issue Created → agents:optimize (quality) → agents:apply-suggestions (format)
                                                        ↓
   User adds agent:codex → capability_check.py runs → If NOT capable:
                                                        → Add needs-human label
                                                        → Post blocker explanation
                                                      If capable:
                                                        → Proceed with agent
   ```

3. **Implementation tasks:**
   - [ ] Create `agents-capability-check.yml` workflow
   - [ ] Add `needs-human` label to consumer repos via sync
   - [ ] Trigger on `agent:codex` label added OR new workflow label
   - [ ] Post comment explaining blockers when agent cannot proceed

**Step 3B: Task Decomposition**

1. **Implementation tasks:**
   - [ ] Create `agents-decompose.yml` workflow
   - [ ] Add `agents:decompose` label to label sync config
   - [ ] Call `task_decomposer.py` when label applied
   - [ ] Output: Either create sub-issues OR add checklist to parent

**Step 3C: Duplicate Detection (Testing Focus)**

1. **Critical concern:** False positives - we don't want to close valid issues
2. **Approach:** Comment-only mode first, no auto-close
3. **Implementation tasks:**
   - [ ] Create `agents-dedup.yml` workflow
   - [ ] Trigger on issue opened
   - [ ] Compare against open issues using embeddings
   - [ ] Post comment if >85% similarity detected (link to potential duplicate)
   - [ ] Track false positive rate over testing period

4. **Testing metrics to track:**
   - True positive rate (correctly identified duplicates)
   - False positive rate (target: <5%)
   - Human override rate (user keeps both issues open)

**Step 3D: Semantic Label Matching**

1. **Implementation tasks:**
   - [ ] Create `agents-auto-label.yml` workflow OR integrate into existing
   - [ ] Use `label_matcher.py` for semantic similarity
   - [ ] Post comment with suggestions OR auto-apply at >90% confidence

---

## Phase 3 Testing Plan (Manager-Database)

**Test Repository:** Manager-Database
**Test Duration:** 2 weeks (7 issues minimum)
**Start Date:** Ready to begin (all consumer repos synced)

### Test Issue #1: Capability Check Validation

**Purpose:** Validate capability_check.py correctly identifies agent blockers

**Test Scenarios:**
1. **Issue requiring external API** - Should flag "needs credentials/external dependency"
2. **Issue requiring database migration** - Should flag "needs infrastructure/manual step"
3. **Normal code-only issue** - Should pass capability check

**Test Issue Ideas for Manager-Database:**
- "Integrate with external payment API" (should fail - external dep)
- "Add database migration for new schema" (should fail - infra)
- "Refactor logging module" (should pass - code only)

### Test Issue #2: Task Decomposition Validation

**Purpose:** Validate task_decomposer.py produces useful sub-tasks

**Test Scenario:**
- Create large issue with 5+ implied tasks
- Apply `agents:decompose` label
- Verify sub-tasks are actionable and correctly scoped

**Test Issue Idea:**
- "Implement comprehensive health check endpoint with retry logic, circuit breaker, metrics, and alerting integration"

### Test Issue #3: Duplicate Detection Validation

**Purpose:** Measure false positive rate for issue_dedup.py

**Test Scenarios:**
1. **True duplicate** - Create issue very similar to existing (should detect)
2. **Related but different** - Create issue in same area but different ask (should NOT flag)
3. **Unrelated** - Create issue in different area (should NOT flag)

**Success Criteria:**
- True positives detected: 100%
- False positive rate: <5%
- Clear explanation in comment linking to potential duplicate

### Test Issue #4: Label Matching Validation

**Purpose:** Validate label_matcher.py suggests correct labels

**Test Scenario:**
- Create unlabeled issues in different categories
- Verify label suggestions match expected labels
- Track suggestion accuracy

### Testing Metrics Dashboard

| Script | Test Issues | True Positives | False Positives | Accuracy | Status |
|--------|-------------|----------------|-----------------|----------|--------|
| capability_check.py | 0/3 | - | - | - | ⏳ Pending |
| task_decomposer.py | 0/2 | - | - | - | ⏳ Pending |
| issue_dedup.py | 0/3 | - | - | <5% target | ⏳ Pending |
| label_matcher.py | 0/3 | - | - | - | ⏳ Pending |

**Total test issues needed:** ~11 issues on Manager-Database

---

## Summary

| Phase | Scope | Steps | Test Repo | Status |
|-------|-------|-------|-----------|--------|
| 1 | PR Verification | 2 | Manager-Database | ✅ Deployed, 6/7 repos synced |
| 2 | Issue Formatting | 1 | Manager-Database | ✅ Deployed & tested - Quality: 7.5/10 |
| 3 | Pre-Agent Intelligence | 4 | Manager-Database | 🔄 Planning - Testing cycle defined |

**Phase 3 Components:**
- **3A:** Capability Check - Pre-agent feasibility gate (supplements agents:optimize)
- **3B:** Task Decomposition - Auto-split large issues
- **3C:** Duplicate Detection - Comment-only mode, track false positives
- **3D:** Semantic Labeling - Auto-suggest/apply labels

**Total: 7 deployment actions** - Phases 1-2 deployed. Phase 3 testing plan defined for Manager-Database (~11 test issues).

**Substantive Quality Assessment:**
- **agents:optimize:** 8.6/10 - Provides valuable, actionable analysis
- **agents:apply-suggestions:** 6/10 → Expected 8.5/10 after enabling LLM
- **Overall:** 7.5/10 → Expected 8.5/10 - Analysis is excellent; application now uses LLM

---

## Remaining Tasks

### Immediate (Ready Now)
1. ~~**Merge PR #633**~~ ✅ Merged - GPT-5.2 for compare mode
2. ~~**Merge PR #643**~~ ✅ Merged - Model name in comparison reports + disable auto-issue creation
3. ~~**Consumer repo sync cleanup**~~ ✅ Completed 2026-01-07 - 26 superseded PRs closed, 6/6 merged
4. ~~**Resolve Collab-Admin sync**~~ ✅ PR #113 merged 2026-01-07
5. ~~**Live test `agents:optimize`**~~ ✅ Tested on Manager-Database #184 - Quality: 8.6/10
6. ~~**Live test `agents:apply-suggestions`**~~ ✅ Tested on Manager-Database #184 - Quality: 6/10

### High Priority Enhancements
1. ~~**Enable LLM for apply_suggestions**~~ ✅ Changed `use_llm=False` to `use_llm=True` in workflow
   - Will populate Tasks with suggested splits from analysis
   - Will extract Why/Scope/Non-Goals from context
   - Will add objective acceptance criteria from suggestions
   - **Impact:** Expected to increase quality score from 6/10 to ~8.5/10
   - **Status:** Deployed, pending retest on Manager-Database

2. **Add task priority/ordering** - LLM could suggest task dependencies
   - "Implement logging before health checks"
   - "Retry logic blocks enhanced error logging"

### Phase 3 Implementation (Next)
1. **Step 3A: Capability Check** - Create `agents-capability-check.yml`, integrate with issue workflow
   - Supplements existing agents:optimize (quality) with feasibility gate
   - Runs BEFORE agent assignment, not after
2. **Step 3B: Task Decomposition** - Create `agents-decompose.yml` workflow
3. **Step 3C: Duplicate Detection** - Create `agents-dedup.yml` (comment-only, track false positives)
4. **Step 3D: Label Matching** - Integrate into issue workflow

### Future Enhancements
1. **Compare mode refinement** - Currently uses gpt-4o (GitHub) vs gpt-5.2 (OpenAI)
2. **Model auto-update** - Use `scripts/update_model_list.sh` periodically
3. **Domain-specific guidance** - Add prompts for retry patterns, health check endpoints

### Test Results Documentation
Full substantive analysis available at `/tmp/substantive_test_analysis.md`:
- Task splitting quality: 9/10 (concrete, verifiable subtasks)
- Objective criteria suggestions: 9.5/10 (numeric thresholds, measurable)
- Structural analysis: 10/10 (accurate section identification)
- Apply-suggestions: 6/10 (structure without intelligent content)
