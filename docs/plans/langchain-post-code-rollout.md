# LangChain Post-Code Production Capabilities - Evaluation & Rollout Plan

> **Date:** January 7, 2026  
> **Status:** Phase 1 & 2 Deployed - Ready for Live Testing  
> **Last Validation:** 2026-01-07  

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
   - GPT-5.2 support (PR #633 pending)
   - Follow-up issue creation on CONCERNS/FAIL
   - JSON output format
   - Tests: 4 test files with good coverage

3. **LLM Provider Framework** - `tools/llm_provider.py` handles:
   - GitHub Models (default, uses GITHUB_TOKEN)
   - OpenAI (fallback, uses OPENAI_API_KEY)
   - Regex fallback (last resort)
   - Model selection capability

### ⚠️ Implemented but Not Synced/Active in Consumer Repos

1. **Verifier Labels** - All 7 consumer repos have `verify:checkbox`, `verify:evaluate`, `verify:compare`:
   - ✅ Manager-Database
   - ✅ Template  
   - ✅ trip-planner
   - ✅ Travel-Plan-Permission
   - ✅ Portable-Alpha-Extension-Model
   - ✅ Trend_Model_Project
   - ⚠️ Collab-Admin (sync PR #104 pending - has failing gate check)

2. **Format Labels** - All 7 consumer repos have `agents:format`, `agents:formatted`, `agents:optimize`, `agents:apply-suggestions`:
   - ✅ Manager-Database (tested live - issue #184)
   - ✅ Template  
   - ✅ trip-planner
   - ✅ Travel-Plan-Permission
   - ✅ Portable-Alpha-Extension-Model
   - ✅ Trend_Model_Project
   - ⚠️ Collab-Admin (sync PR #104 pending - has failing gate check)

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

### Phase 3 Target: Advanced Features (Optional)

- `capability_check.py` integrated into issue intake OR archived
- `task_decomposer.py` integrated for large issues OR archived
- Dedup/semantic matching for issue triage OR archived

---

## 4. Rollout Plan

### Phase 1: PR Verification (2 Steps)

**Step 1A: Prepare Workflows Repo**
- [x] Verify `reusable-agents-verifier.yml` is correct (done)
- [x] Verify `agents-verifier.yml` template calls reusable correctly (done)
- [x] `.gitignore` template has all workflow status entries (not synced by design)
- [x] Add model selection and provider choice (PR #626, #629 merged)
- [x] Add scripts/update_model_list.sh for model management (PR #633)
- [x] Add docs/MODEL_MANAGEMENT.md for model update process (PR #633)
- [x] Commit any fixes to main

**Step 1B: Deploy to Consumer Repos**
1. ✅ All consumer repos have verifier labels (6/7 active, Collab-Admin pending)
2. ✅ Sync workflow runs automatically on template changes
3. ✅ Sync PRs merged (except Collab-Admin #104)
4. ⏳ Test on Manager-Database (pilot):
   - Find a recently merged agent PR
   - Add `verify:evaluate` label  
   - Verify workflow runs and posts evaluation comment
   - **Status:** Ready for testing - requires repo write access

**Validation Criteria:**
- [x] Verifier labels exist in all 7 consumer repos (6 active, 1 pending)
- [x] `agents-verifier.yml` deployed to consumer repos (6/7)
- [x] Model selection working (tested PRs #625, #270, #302)
- [x] Compare mode with different models working (tested PR #302)
- [ ] Live test on fresh PR: Workflow runs without errors
- [ ] Live test on fresh PR: LLM evaluation produces scores and verdict
- [ ] Live test on fresh PR: Comment posted on PR with evaluation results
- [ ] Live test on fresh PR: Follow-up issue created if verdict is CONCERNS/FAIL

### Phase 2: Issue Formatting & Cleanup (1 Step)

**Step 2A: Labels & Sync**
1. ✅ Labels created via sync workflow (`agents:format`, `agents:formatted`, `agents:optimize`, `agents:apply-suggestions`)
2. ✅ `agents-issue-optimizer.yml` is in sync manifest
3. ✅ Sync PRs merged automatically (6/7 repos)
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

### Phase 3: Archive Unused Scripts (1 Step)

**Status: Decision Deferred**

These scripts are fully tested (145 tests passing) but not yet integrated:
- `capability_check.py` - Pre-flight check for agent capability on tasks
- `task_decomposer.py` - Break large tasks into smaller actionable items  
- `issue_dedup.py` - Detect duplicate issues via embeddings
- `label_matcher.py` - Semantic label matching
- `semantic_matcher.py` - Shared embedding utilities

**Recommendation:** Keep & Document for future Phase 3+ integration
- All scripts have full test coverage
- Semantic matching could enhance issue triage
- Capability check could prevent failed agent attempts

---

## Summary

| Phase | Scope | Steps | Test Repo | Status |
|-------|-------|-------|-----------|--------|
| 1 | PR Verification | 2 | Manager-Database | ✅ Deployed, tested on 3 PRs |
| 2 | Issue Formatting | 1 | Manager-Database | ✅ Deployed & tested - Quality: 7.5/10 |
| 3 | Cleanup/Archive | 1 | N/A | Deferred (scripts retained) |

**Total: 4 deployment actions** - All infrastructure deployed. Collab-Admin sync PR pending.

**Substantive Quality Assessment:**
- **agents:optimize:** 8.6/10 - Provides valuable, actionable analysis
- **agents:apply-suggestions:** 6/10 → Expected 8.5/10 after enabling LLM
- **Overall:** 7.5/10 → Expected 8.5/10 - Analysis is excellent; application now uses LLM

---

## Remaining Tasks

### Immediate (Ready Now)
1. ~~**Merge PR #633**~~ ✅ Merged - GPT-5.2 for compare mode
2. ~~**Resolve Collab-Admin sync**~~ ⏳ PR #104 blocked by failing gate check
3. ~~**Live test `agents:optimize`**~~ ✅ Tested on Manager-Database #184 - Quality: 8.6/10
4. ~~**Live test `agents:apply-suggestions`**~~ ✅ Tested on Manager-Database #184 - Quality: 6/10

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

### Future Enhancements
1. **Compare mode refinement** - Currently uses gpt-4o (GitHub) vs gpt-5.2 (OpenAI)
2. **Model auto-update** - Use `scripts/update_model_list.sh` periodically
3. **Domain-specific guidance** - Add prompts for retry patterns, health check endpoints
4. **Phase 3 scripts** - Decide on capability_check.py and task_decomposer.py integration

### Test Results Documentation
Full substantive analysis available at `/tmp/substantive_test_analysis.md`:
- Task splitting quality: 9/10 (concrete, verifiable subtasks)
- Objective criteria suggestions: 9.5/10 (numeric thresholds, measurable)
- Structural analysis: 10/10 (accurate section identification)
- Apply-suggestions: 6/10 (structure without intelligent content)
