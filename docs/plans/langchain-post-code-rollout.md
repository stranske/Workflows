# LangChain Post-Code Production Capabilities - Evaluation & Rollout Plan

> **Date:** January 6, 2026  
> **Status:** Assessment Complete  

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
   - Single-provider evaluation mode
   - Multi-provider comparison mode
   - Follow-up issue creation on CONCERNS/FAIL
   - JSON output format
   - Tests: 4 test files with good coverage

3. **LLM Provider Framework** - `tools/llm_provider.py` handles:
   - GitHub Models (default, uses GITHUB_TOKEN)
   - OpenAI (fallback, uses OPENAI_API_KEY)
   - Regex fallback (last resort)
   - Model selection capability

### ⚠️ Implemented but Not Synced/Active in Consumer Repos

1. **Verifier Labels** - Only 3 of 7 consumer repos have `verify:checkbox`, `verify:evaluate`, `verify:compare`:
   - ✅ Manager-Database
   - ✅ Template  
   - ✅ trip-planner
   - ❌ Travel-Plan-Permission
   - ❌ Portable-Alpha-Extension-Model
   - ❌ Trend_Model_Project
   - ❌ Collab-Admin

2. **Format Labels** - Only 3 of 7 consumer repos have `agents:format`, `agents:formatted`:
   - ✅ Manager-Database
   - ✅ Template
   - ✅ trip-planner
   - ❌ Others

3. **Updated .gitignore** - Consumer repos have old partial version, missing new entries for:
   - `verifier-diff-summary.md`
   - `autofix_report_enriched.json`
   - Various metrics files

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
- [ ] Verify `reusable-agents-verifier.yml` is correct (done)
- [ ] Verify `agents-verifier.yml` template calls reusable correctly (done)
- [ ] Add `.gitignore` to sync manifest if missing
- [ ] Commit any fixes to main

**Step 1B: Deploy to Consumer Repos**
1. Run `python scripts/create_verifier_labels.py --all` to create labels in all consumer repos
2. Trigger sync workflow to push updated templates
3. Wait for sync PRs, merge via `Merge Sync PRs` workflow
4. Test on Manager-Database (pilot):
   - Find a recently merged PR
   - Add `verify:evaluate` label
   - Verify workflow runs and posts evaluation comment

**Validation Criteria:**
- [ ] Workflow runs without errors
- [ ] LLM evaluation produces scores and verdict
- [ ] Comment posted on PR with evaluation results
- [ ] Follow-up issue created if verdict is CONCERNS/FAIL

### Phase 2: Issue Formatting & Cleanup (1 Step)

**Step 2A: Labels & Sync**
1. Run label creation script for `agents:format`, `agents:formatted` across all repos
2. Verify `agents-issue-optimizer.yml` is in sync manifest
3. Trigger sync and merge PRs
4. Test on Manager-Database:
   - Create test issue with unformatted content
   - Add `agents:format` label
   - Verify issue is reformatted and `agents:formatted` label added

**Validation Criteria:**
- [ ] `agents:format` triggers workflow
- [ ] Issue body updated to AGENT_ISSUE_TEMPLATE
- [ ] `agents:formatted` label added
- [ ] Original content preserved in hidden section

### Phase 3: Archive Unused Scripts (1 Step)

After Phases 1-2 validated:
1. Review `capability_check.py`, `task_decomposer.py`, `issue_dedup.py`, `label_matcher.py`, `semantic_matcher.py`
2. Decision for each:
   - **Keep & Document**: If planned for future integration
   - **Archive**: Move to `scripts/langchain/experimental/` with README
3. Update sync manifest to only include production scripts

---

## Summary

| Phase | Scope | Steps | Test Repo |
|-------|-------|-------|-----------|
| 1 | PR Verification | 2 | Manager-Database |
| 2 | Issue Formatting | 1 | Manager-Database |
| 3 | Cleanup/Archive | 1 | N/A |

**Total: 4 deployment actions** instead of many one-offs.
