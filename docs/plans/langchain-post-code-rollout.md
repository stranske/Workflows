# LangChain Post-Code Production Capabilities - Evaluation & Rollout Plan

> **Date:** January 7, 2026  
> **Status:** Phase 4 Planning - Full Automation Design  
> **Last Validation:** 2026-01-07 (Phase 4 Planning Added)  

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

### Test Issues Created (Manager-Database)

| Issue | Purpose | Expected Result |
|-------|---------|-----------------|
| #193 | Capability Check - External service (Stripe) | ❌ SHOULD FAIL - requires Stripe API credentials, webhook endpoint |
| #194 | Task Decomposition - Large issue (10 tasks) | ✅ SHOULD DECOMPOSE - into 3-5 sub-issues or checklist |
| #196 | Duplicate Detection - Similar to #133 | ⚠️ SHOULD DETECT - ~85%+ similarity to "Add GET Endpoint for Managers List" |

### Testing Metrics Dashboard

| Script | Test Issues | True Positives | False Positives | Accuracy | Status |
|--------|-------------|----------------|-----------------|----------|--------|
| capability_check.py | #193 (1/3) | - | - | - | 🔄 Testing |
| task_decomposer.py | #194 (1/2) | - | - | - | 🔄 Testing |
| issue_dedup.py | #196 (1/3) | - | - | <5% target | 🔄 Testing |
| label_matcher.py | 0/3 | - | - | - | ⏳ Pending |

**Total test issues created:** 3/11 on Manager-Database

---

## Summary

| Phase | Scope | Steps | Test Repo | Status |
|-------|-------|-------|-----------|--------|
| 1 | PR Verification | 2 | Manager-Database | ✅ Deployed, 7/7 repos synced |
| 2 | Issue Formatting | 1 | Manager-Database | ✅ Deployed & tested - Quality: 7.5/10 |
| 3 | Pre-Agent Intelligence | 4 | Manager-Database | 🔄 Testing - 3/11 test issues created |
| 4 | Full Automation & Cleanup | 5 | Manager-Database | 📋 Planning |

**Phase 3 Components:**
- **3A:** Capability Check - Pre-agent feasibility gate (supplements agents:optimize)
- **3B:** Task Decomposition - Auto-split large issues
- **3C:** Duplicate Detection - Comment-only mode, track false positives
- **3D:** Semantic Labeling - Auto-suggest/apply labels

**Phase 4 Components:**
- **4A:** Label Cleanup - Remove bloat, standardize across repos
- **4B:** User Guide - Operational documentation for label system
- **4C:** Auto-Pilot Label - End-to-end issue-to-merge automation
- **4D:** Conflict Resolution - Automated merge conflict handling in keepalive
- **4E:** Verify-to-Issue - Create follow-up issues from verification feedback

**Total: 12 deployment actions** - Phases 1-2 deployed. Phases 3-4 in planning/testing.

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

---

## Phase 4: Full Automation & Cleanup (5 Initiatives)

> **Status:** Planning  
> **Goal:** Streamline end-to-end automation from issue to merged PR

### 4A. Label Cleanup & Standardization

**Problem:** Consumer repos have accumulated label bloat (30+ labels in some repos) with many unused/redundant labels like `stage 0`, `codex`, `ai:agent`, etc.

**Idiosyncratic Repo Bloat Strategy:**
Each consumer repo has accumulated repo-specific labels (e.g., `architecture`, `backend`, `cli`, `config`, `data`, `engine`, `app`) that aren't synced and aren't used by automation. These create visual clutter and confusion about which labels have functional effects.

**Cleanup approach:**
1. **Audit each repo** - List all labels not in canonical set
2. **Classify** - Determine if repo-specific label is:
   - Used in repo-specific workflows (keep)
   - Used for human categorization (optional keep - user choice)
   - Unused/obsolete (remove)
3. **Create per-repo cleanup PR** - With list of labels to remove and justification
4. **Human approval required** - Repo maintainer reviews and approves before execution

**Functional Labels (Keep - Have Workflow Effects):**

| Label | Trigger | Applies To | Used By |
|-------|---------|------------|---------|
| `agent:codex` | Issue intake, keepalive | Issues, PRs | `agents-issue-intake.yml`, `agents-keepalive-loop.yml` |
| `agent:claude` | Issue intake (future) | Issues, PRs | `agents-issue-intake.yml` |
| `agent:copilot` | Issue intake (future) | Issues, PRs | `agents-issue-intake.yml` |
| `agent:needs-attention` | Auto-applied when stuck | Issues, PRs | Multiple workflows |
| `agents` (bare) | Issue template auto-label | Issues | `agent_task.yml` template |
| `agents:format` | Direct formatting | Issues | `agents-issue-optimizer.yml` |
| `agents:formatted` | Auto-applied after format | Issues | `agents-issue-optimizer.yml` |
| `agents:optimize` | Analyze + suggest | Issues | `agents-issue-optimizer.yml` |
| `agents:apply-suggestions` | Apply suggestions | Issues | `agents-issue-optimizer.yml` |
| `agents:allow-change` | Override agents-guard | PRs | `agents-guard.yml` |
| `agents:keepalive` | Enable keepalive loop | PRs | `agents-keepalive-loop.yml` |
| `agents:activated` | Track first human activation | PRs | `agents_pr_meta_keepalive.js` |
| `agents:paused` | Pause/paused keepalive | PRs | `keepalive_gate.js`, `keepalive-runner.js` |
| `autofix` | Trigger autofix | PRs | `autofix.yml` |
| `autofix:clean` | Aggressive autofix | PRs | `autofix.yml` |
| `autofix:bot-comments` | Address bot comments | PRs | `agents-bot-comment-handler.yml` |
| `autofix:applied` | Auto-applied | PRs | Autofix workflows |
| `automerge` | Enable auto-merge | PRs | `merge_manager.js`, `agents_belt_scan.js` |
| `from:codex` | Track PR origin | PRs | `merge_manager.js` |
| `from:copilot` | Track PR origin | PRs | `merge_manager.js` |
| `risk:low` | Low-risk for auto-approve | PRs | `merge_manager.js` |
| `ci:green` | CI status tracking | PRs | `merge_manager.js` |
| `codex-ready` | Ready for Codex | Issues | Issue templates |
| `verify:checkbox` | Checkbox verification | PRs (merged) | `agents-verifier.yml` |
| `verify:evaluate` | LLM evaluation | PRs (merged) | `agents-verifier.yml` |
| `verify:compare` | Multi-model comparison | PRs (merged) | `agents-verifier.yml` |
| `needs-human` | Human intervention needed | Issues, PRs | Multiple workflows |
| `sync` | From sync workflow | PRs | Sync workflows |
| `automated` | Bot-created | Issues, PRs | Multiple workflows |
| `coverage` | Coverage issue tracking | Issues | `maint-coverage-guard.yml` |

**Informational Labels (Keep - Useful Categorization):**

| Label | Purpose |
|-------|---------|
| `bug` | Bug reports |
| `enhancement` | Feature requests |
| `documentation` | Doc changes |
| `duplicate` | Duplicate tracking |
| `wontfix` | Won't address |

**Labels to Remove (Verified No Functional Effect):**

| Label | Reason | Searched | Result |
|-------|--------|----------|--------|
| `codex` (bare) | Redundant with `agent:codex` | ✅ | No workflow triggers on this |
| `agents:pause` | Redundant with `agents:paused` | ✅ | Consolidated to `agents:paused` |
| `ai:agent` | Redundant | ✅ | Zero matches in codebase |
| `auto-merge-audit` | Unused | ✅ | Zero matches in codebase |
| `automerge:ok` | Unused variant | ✅ | Zero matches in codebase |

**⚠️ CORRECTED from initial analysis:** The following labels ARE functional and should NOT be removed:
- `agents` (bare) - Used by issue templates
- `agents:activated` - Tracks human activation state
- `agents:paused` - Controls keepalive pausing (consolidated from agents:pause)
- `automerge` - Enables auto-merge in merge_manager.js
- `from:codex` / `from:copilot` - Used by merge_manager.js for origin tracking
- `risk:low` / `ci:green` / `codex-ready` - Used by merge_manager and issue templates

**Implementation:**
- [ ] Create `scripts/cleanup_labels.py` to remove ONLY verified bloat labels
- [ ] Audit each consumer repo for idiosyncratic labels
- [ ] Create per-repo cleanup PR with human approval gate
- [ ] Update `docs/LABELS.md` with canonical label list
- [ ] Add label validation to sync workflow

### 4B. Workflow User Guide Document

> **Status:** Deferred until Phases 4A, 4C-4E complete

**Problem:** Users don't know how to use the label system effectively.

**Solution:** Create `docs/WORKFLOW_USER_GUIDE.md` with:

1. **Quick Start** - Most common workflows with copy-paste examples
2. **Issue Creation Flow** - Step-by-step from idea to formatted issue
3. **PR Automation Flow** - How labels progress a PR to merge
4. **Label Decision Tree** - "What label should I add?"
5. **Troubleshooting** - Common issues and solutions
6. **Optional: Issue Creation from Doc** - Command/workflow to create issue from guide sections

**Sections:**

```markdown
## Creating an Agent-Ready Issue

1. Create issue with rough description
2. Add `agents:optimize` label → Review suggestions
3. Add `agents:apply-suggestions` label → Issue formatted
4. Add `agent:codex` label → Agent starts work

## Monitoring Agent Progress

- Check PR for `agent:needs-attention` label
- Review keepalive comments for status
- Add `autofix` if CI failing on simple issues

## Post-Merge Verification

- Add `verify:evaluate` after merge for LLM review
- Add `verify:compare` for multi-model comparison
```

**Optional Issue Creation Feature:**
```markdown
## Quick Issue from Guide

At end of each workflow section, include:
- "Create issue to implement this" link
- Pre-populated with section content as template
- Links back to guide for context
```

**Implementation:**
- [ ] Create `docs/WORKFLOW_USER_GUIDE.md`
- [ ] Add to sync-manifest.yml
- [ ] Add prominent link in each repo's README
- [ ] Consider GitHub wiki integration
- [ ] **Optional:** Add issue creation links per section

### 4C. Master Automation Label (`agents:auto-pilot`)

**Goal:** Single label for complete issue-to-merged-PR automation.

**Proposed Flow:**

```
User adds `agents:auto-pilot` to issue
          ↓
Step 1: agents:format (initial structure)
          ↓
Step 2: agents:optimize → agents:apply-suggestions
          ↓
Step 3: capability_check.py runs
          ↓ (if capable)
Step 4: agent:codex applied → PR created
          ↓
Step 5: autofix + agents:keepalive applied to PR
          ↓
Step 6: Gate passes + acceptance criteria met
          ↓
Step 7: Auto-merge (if enabled + all checks pass)
          ↓
Step 8: verify:evaluate on merged PR
```

**Feasibility Analysis:**

| Step | Challenge | Mitigation |
|------|-----------|------------|
| Sequential labels | GitHub doesn't support chained label triggers | Use workflow_dispatch between steps |
| Race conditions | Multiple workflows competing | Concurrency groups + state tracking |
| Error handling | What if step fails? | Add `agents:auto-pilot-failed` + comment explaining failure |
| User expectations | Users expect instant completion | Post progress comments at each step |
| Rollback | What if we need to stop? | `agents:auto-pilot-pause` label |

**Major Risks:**
1. **Runaway automation** - Agent creates bad PR, auto-merges, creates more issues
   - Mitigation: Max iterations, human approval gates for auto-merge
2. **CI instability** - Flaky tests block automation indefinitely
   - Mitigation: Timeout after N keepalive cycles, escalate to `needs-human`
3. **Token exhaustion** - Long sessions burn through LLM quota
   - Mitigation: Per-issue token budget tracking

**Implementation:**
- [ ] Design state machine for auto-pilot flow
- [ ] Create `agents-auto-pilot.yml` orchestrator workflow
- [ ] Add progress tracking comments
- [ ] Implement failure handling and rollback
- [ ] Add `agents:auto-pilot-pause` for manual intervention
- [ ] Test on Manager-Database with controlled issues

### 4D. Conflict Resolution in Keepalive

**Problem:** Most common reason keepalive stalls is merge conflicts. Agents handle conflicts well when prompted, but current pipeline doesn't automatically detect/respond.

**Current State:**
- Keepalive detects "Gate failed" but doesn't distinguish conflict from test failure
- Agent eventually addresses conflicts but wastes cycles

**Full Implementation Plan:**

**Step 1: Conflict Detection Module**
Create `scripts/conflict_detector.js`:
```javascript
// Detect merge conflicts via git status and CI logs
async function detectConflicts(github, context, prNumber) {
  // Method 1: Check GitHub's mergeable_state
  const pr = await github.rest.pulls.get({
    owner: context.repo.owner,
    repo: context.repo.repo,
    pull_number: prNumber
  });
  
  if (pr.data.mergeable_state === 'dirty') {
    return { hasConflict: true, source: 'github-api' };
  }
  
  // Method 2: Parse CI logs for conflict markers
  const runs = await github.rest.actions.listWorkflowRunsForRepo({...});
  // Look for: "CONFLICT", "merge conflict", "Automatic merge failed"
  
  return { hasConflict: false };
}
```

**Step 2: Update Keepalive Gate**
Modify `keepalive_gate.js`:
```javascript
// After gate failure, check if conflict
const conflictResult = await detectConflicts(github, context, prNumber);
if (conflictResult.hasConflict) {
  core.setOutput('skip_reason', 'merge-conflict');
  core.setOutput('conflict_files', conflictResult.files.join(', '));
  // Trigger conflict-specific prompt
  return;
}
```

**Step 3: Conflict Resolution Prompt**
Create `.github/codex/prompts/fix_merge_conflicts.md`:
```markdown
# Task: Resolve Merge Conflicts

This PR has merge conflicts that need to be resolved.

## Conflict Files
{{conflict_files}}

## Instructions
1. Fetch the latest changes from main/master branch
2. Identify and resolve each conflict, keeping the intent of both changes
3. Run tests to ensure resolution doesn't break functionality
4. Commit with message: "fix: resolve merge conflicts with main"

## Priority
- Prefer the PR's changes when semantically equivalent
- If main has breaking changes, adapt PR code to new API
- When in doubt, keep both changes if they're additive
```

**Step 4: Integration with Keepalive Loop**
Add to `agents-keepalive-loop.yml`:
```yaml
- name: Check for conflicts
  id: conflict-check
  uses: ./.github/actions/conflict-detector
  with:
    pr_number: ${{ inputs.pr_number }}

- name: Use conflict prompt if needed
  if: steps.conflict-check.outputs.has_conflict == 'true'
  run: |
    echo "prompt_override=fix_merge_conflicts.md" >> $GITHUB_OUTPUT
```

**Step 5: Metrics & Logging**
- Track: conflicts detected, conflicts resolved, resolution time
- Log: conflict files, resolution commits, manual escalations

**Implementation Checklist:**
- [ ] Create `scripts/conflict_detector.js`
- [ ] Add conflict detection to `keepalive_gate.js`
- [ ] Create `.github/codex/prompts/fix_merge_conflicts.md`
- [ ] Update `agents-keepalive-loop.yml` to use conflict prompt
- [ ] Add conflict metrics to keepalive summary
- [ ] Create `error_classifier.js` enhancements for conflict patterns
- [ ] Test with intentionally conflicted branches on Manager-Database

### 4E. Verification-to-Issue Workflow

**Problem:** When `verify:evaluate` or `verify:compare` identifies issues, there's no automated way to create follow-up work.

**Note:** We previously disabled automatic issue creation because it was too aggressive. This is a **user-triggered** alternative.

**Proposed Label:** `verify:create-issue`

**Flow:**

```
User reviews verify comment on merged PR
          ↓
User adds `verify:create-issue` label
          ↓
Workflow extracts:
  - CONCERNS from evaluation report
  - Specific scores <7/10
  - Unique insights from comparison
          ↓
Creates new issue:
  - Title: "[Follow-up] {concern summary} from PR #{number}"
  - Body: Structured with original PR link, specific concerns, suggested tasks
  - Labels: `agents:optimize` (ready for agent formatting)
          ↓
Posts comment on PR linking to new issue
```

**Full Implementation:**

**Create `agents-verify-to-issue.yml`:**
```yaml
name: Create Issue from Verification

on:
  pull_request:
    types: [labeled]

jobs:
  create-issue:
    if: github.event.label.name == 'verify:create-issue'
    runs-on: ubuntu-latest
    steps:
      - name: Find verification comment
        id: find-comment
        uses: peter-evans/find-comment@v3
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body-includes: "## PR Verification Report"
      
      - name: Extract concerns
        id: extract
        uses: actions/github-script@v7
        with:
          script: |
            const comment = `${{ steps.find-comment.outputs.comment-body }}`;
            // Parse CONCERNS section
            const concernsMatch = comment.match(/### Concerns\n([\s\S]*?)(?=###|$)/);
            const concerns = concernsMatch ? concernsMatch[1].trim() : 'No specific concerns found';
            
            // Parse low scores
            const scoreMatches = [...comment.matchAll(/(\w+):\s*(\d+)\/10/g)];
            const lowScores = scoreMatches
              .filter(m => parseInt(m[2]) < 7)
              .map(m => `${m[1]}: ${m[2]}/10`);
            
            core.setOutput('concerns', concerns);
            core.setOutput('low_scores', lowScores.join(', ') || 'None below 7/10');
      
      - name: Create follow-up issue
        uses: actions/github-script@v7
        with:
          script: |
            const prNumber = context.payload.pull_request.number;
            const prTitle = context.payload.pull_request.title;
            const concerns = `${{ steps.extract.outputs.concerns }}`;
            const lowScores = `${{ steps.extract.outputs.low_scores }}`;
            
            const issueBody = `## Follow-up from PR #${prNumber}
            
**Original PR:** #${prNumber} - ${prTitle}

## Concerns Identified

${concerns}

## Scores Below Threshold

${lowScores}

## Suggested Tasks

- [ ] Address the concerns listed above
- [ ] Update tests if needed
- [ ] Re-verify after changes

---
*This issue was automatically created from verification feedback. Add \`agents:optimize\` to refine.*`;

            const issue = await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `[Follow-up] Address verification concerns from PR #${prNumber}`,
              body: issueBody,
              labels: ['agents:optimize', 'follow-up']
            });
            
            // Comment on original PR
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: prNumber,
              body: `📋 Follow-up issue created: #${issue.data.number}`
            });
            
            // Remove the trigger label
            await github.rest.issues.removeLabel({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: prNumber,
              name: 'verify:create-issue'
            });
```

**Implementation Checklist:**
- [ ] Create `agents-verify-to-issue.yml` workflow
- [ ] Add `verify:create-issue` label to sync config
- [ ] Add `follow-up` label to sync config
- [ ] Test on Travel-Plan-Permission or Manager-Database
- [ ] Add to sync manifest for consumer repos

---

## Phase 4 Testing Plan

**Test Repository:** Manager-Database  
**Test Duration:** 2 weeks

### Test 4A: Label Cleanup

1. Count labels before cleanup
2. Run cleanup script
3. Verify functional labels still work
4. Confirm bloat labels removed

### Test 4B: User Guide

1. Create guide document
2. Test each documented flow
3. Gather feedback on clarity

### Test 4C: Auto-Pilot (High Risk - Careful Testing)

**Test Issue Ideas:**
- Simple refactoring task (low risk)
- Bug fix with clear acceptance criteria
- NOT: Large features or infrastructure changes

**Success Criteria:**
- Issue → Merged PR in <2 hours (for simple tasks)
- No runaway automation
- Clear progress visibility
- Graceful failure handling

### Test 4D: Conflict Resolution

1. Create PR with intentional conflict
2. Verify conflict detection triggers
3. Confirm agent resolves conflict
4. Measure cycle efficiency improvement

### Test 4E: Verify-to-Issue

1. Use existing verify:evaluate results
2. Add verify:create-issue label
3. Confirm issue created with proper context
4. Verify issue is agent-ready

---

## Additional Automation Opportunities (Phase 5+)

### 5A. Auto-labeling on PR Creation ✅ READY

**Status:** Script exists (`label_matcher.py`), workflow integration needed.

**Script location:** `scripts/langchain/label_matcher.py`
- Uses semantic embeddings to match issue/PR content to labels
- Configurable confidence threshold (default 80%)
- Already has tests in place

**Implementation plan:**
- [ ] Create `agents-auto-label.yml` workflow
- [ ] Trigger on PR opened
- [ ] Call `label_matcher.py` with PR title + body + changed files
- [ ] Apply labels at >90% confidence OR post comment with suggestions

### 5B. Coverage Regression Auto-Issue ✅ EXISTS

**Status:** Already implemented in `maint-coverage-guard.yml`!

**Current behavior:**
- Runs daily on schedule
- Compares current coverage to `config/coverage-baseline.json`
- Creates/updates issue titled "[coverage] baseline breach" when below threshold
- Labels with `coverage`

**Suggested enhancement:** Add soft check to PRs (warn, don't fail)
- [ ] Add optional PR check that posts coverage delta as comment
- [ ] Warning only - does not block merge or automation
- [ ] Shows trend: "Coverage changed: 82% → 79% (-3%)"

### 5C. Stale PR Cleanup ❌ NOT NEEDED

**Decision:** Not an issue in these repos currently. Skip.

### 5D. Dependency Update Automation ⚠️ PARTIAL

**Current state:**
- `maint-dependabot-auto-label.yml` - Adds `agents:allow-change` label to dependabot PRs
- `maint-dependabot-auto-lock.yml` - Regenerates requirements.lock for pyproject.toml changes

**Missing:**
- Auto-merge when CI passes
- Currently dependabot PRs require manual merge

**Implementation plan:**
- [ ] Add auto-merge step to dependabot workflow
- [ ] Condition: CI green + no security alerts + minor/patch version only
- [ ] Skip for major version bumps (require human review)

### 5E. Issue Template Enforcement (Soft Warning)

**Approach:** Warn, don't block.

**Implementation plan:**
- [ ] Create `agents-issue-lint.yml` workflow
- [ ] Trigger on issue opened/edited
- [ ] Check for AGENT_ISSUE_TEMPLATE sections (Why, Scope, Tasks, Acceptance)
- [ ] If missing sections:
  - Post friendly comment suggesting `agents:format` label
  - Add `needs-formatting` label
  - Do NOT close or block the issue

### 5F. Cross-Repo Issue Linking ❌ SKIPPED

**Decision:** Not implementing. Complexity outweighs benefit for current repo scale.

### 5G. Agent Performance Dashboard (LangSmith + Custom)

**Strategy:** Use LangSmith for LLM operations, custom GitHub metrics for workflow stats.

**LangSmith Integration (Recommended for LLM Metrics):**

LangSmith provides out-of-the-box tracking for:
- Token usage per operation (prompt + completion)
- Latency by provider/model
- Success/failure rate by prompt
- Cost tracking per provider
- Trace visualization for debugging

**Implementation:**
```python
# In llm_provider.py - add LangSmith tracing
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = "workflows-agents"

# Traces automatically captured for:
# - pr_verifier.py evaluations
# - issue_optimizer.py analysis
# - issue_formatter.py LLM calls
# - Any future LangChain operations
```

**Custom Workflow Metrics (GitHub-based):**

| Metric | Source | Collection Method |
|--------|--------|-------------------|
| Issues created → PR merged time | Issue/PR timestamps | GitHub API query |
| Keepalive cycles per PR | Workflow run count | Count runs per PR |
| Agent success rate | PR merge status | Merged vs closed without merge |
| Autofix effectiveness | Commits per PR | Count autofix commits |
| CI pass rate first try | Gate workflow | First run success % |
| Conflict resolution time | Conflict detect → resolve | Timestamp diff |

**Implementation Checklist:**
- [ ] Add `LANGSMITH_API_KEY` secret to Workflows repo
- [ ] Update `tools/llm_provider.py` with tracing env vars
- [ ] Create LangSmith project "workflows-agents"
- [ ] Create `scripts/agent_metrics.py` for GitHub API stats
- [ ] Add `maint-agent-metrics.yml` weekly workflow
- [ ] Output: Post summary to wiki or store in repo

**Dashboard Views:**
1. **LangSmith Dashboard:** Token usage, latency, errors by model/prompt
2. **GitHub Actions Insights:** Workflow run times, success rates
3. **Custom Metrics Report:** Weekly summary posted to wiki/README

---

## Implementation Priority

| Initiative | Effort | Value | Priority | Notes |
|------------|--------|-------|----------|-------|
| 4A. Label Cleanup | Low | Medium | ✅ Ready | 5 bloat labels + per-repo audit |
| 4B. User Guide | Medium | High | Defer | After other features stable |
| 4C. Auto-Pilot | High | High | Test carefully | Most complex |
| 4D. Conflict Resolution | Medium | High | ✅ Ready | Full implementation planned |
| 4E. Verify-to-Issue | Low | Medium | ✅ Ready | Full workflow designed |
| 5A. Auto-labeling | Low | Medium | ✅ Ready | Script exists |
| 5B. Coverage PR Check | Low | Medium | ✅ Ready | Soft warning only |
| 5D. Dependabot Auto-merge | Low | Medium | ✅ Ready | Extend existing |
| 5E. Issue Lint | Low | Low | Later | Nice to have |
| 5F. Cross-Repo Linking | - | - | ❌ Skipped | Not needed |
| 5G. Metrics Dashboard | Medium | Medium | ✅ Ready | LangSmith + custom |

### Test Results Documentation
Full substantive analysis available at `/tmp/substantive_test_analysis.md`:
- Task splitting quality: 9/10 (concrete, verifiable subtasks)
- Objective criteria suggestions: 9.5/10 (numeric thresholds, measurable)
- Structural analysis: 10/10 (accurate section identification)
- Apply-suggestions: 6/10 (structure without intelligent content)
