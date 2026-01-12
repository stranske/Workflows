# LangChain Issue Intake - Rollout Task List

> **Created:** January 5, 2026  
> **Status:** Historical task tracker (may be partially superseded)  
> **Tracking Issue:** #484

> **Last reviewed:** 2026-01-11
> **Canonical references:** `docs/ci/WORKFLOW_SYSTEM.md` and `templates/consumer-repo/` for the current consumer wiring.

---

## Overview

This document tracks the tasks required to roll out the LangChain issue intake enhancements to consumer repositories.

## Phase 1: Core Formatter Rollout

### Prerequisites

- [x] Core `issue_formatter.py` implemented (#478)
- [x] Fallback formatting works without LLM
- [x] Basic test coverage verified
- [ ] Add `issue_formatter.py` to sync-manifest.yml

### Workflows Tasks

| Task | Issue | Status |
|------|-------|--------|
| Implement `agents:format` label workflow | #545 | 🔴 Not Started |
| Test `agents:optimize` → `agents:apply-suggestions` flow | - | 🟡 Manual Testing |
| Document workflow in LABELS.md | - | ✅ Done |

### Consumer Repo Label Setup

**Labels to create in each consumer repo:**

| Label | Color | Description |
|-------|-------|-------------|
| `agents:format` | `#0E8A16` (green) | Triggers direct issue formatting |
| `agents:formatted` | `#1D76DB` (blue) | Issue has been formatted to template |
| `agents:optimize` | `#FBCA04` (yellow) | Triggers issue analysis |
| `agents:apply-suggestions` | `#0E8A16` (green) | Applies optimization suggestions |

**Consumer repos to update:**

- [ ] stranske/Portable-Alpha-Extension-Model
- [ ] stranske/Travel-Plan-Permission
- [ ] stranske/Trend_Model_Project
- [ ] (other consumer repos as needed)

### Sync Manifest Updates

Add to `.github/sync-manifest.yml`:

```yaml
# LangChain issue formatting (Phase 1)
- source: scripts/langchain/issue_formatter.py
  description: "Issue formatter - converts raw text to AGENT_ISSUE_TEMPLATE"

- source: scripts/langchain/prompts/format_issue.md
  description: "Prompt template for issue formatting"
```

---

## Phase 2: Full Optimizer Rollout

### Prerequisites

- [x] #540 - Test coverage improved to 70%+
- [ ] `agents:format` workflow implemented (#545)
- [ ] Phase 1 validated on 1-2 consumer repos

### Files to Sync

```yaml
# LangChain optimizer (Phase 2)
- source: scripts/langchain/issue_optimizer.py
  description: "Issue optimizer - analyzes and suggests improvements"

- source: scripts/langchain/capability_check.py
  description: "Agent capability pre-flight check"

- source: scripts/langchain/prompts/analyze_issue.md
  description: "Prompt template for issue analysis"

- source: scripts/langchain/prompts/apply_suggestions.md
  description: "Prompt template for applying suggestions"
```

### Workflow Updates

- [ ] Sync `agents-issue-optimizer.yml` to consumer repos
- [ ] Test on Portable-Alpha-Extension-Model first
- [ ] Roll out to remaining consumer repos

---

## Phase 3: Full LangChain Module Sync

### Prerequisites

- [ ] Phase 2 validated on 3+ consumer repos
- [ ] All edge cases documented
- [ ] Rollback procedures tested

### Files to Sync

```yaml
# Full LangChain module directory (Phase 3)
- source: scripts/langchain/
  is_directory: true
  description: "Full LangChain module suite for issue intake"
```

### Additional Components

- [ ] `task_decomposer.py` - Large task splitting
- [ ] `issue_dedup.py` - Duplicate detection
- [ ] `context_extractor.py` - PR context injection
- [ ] `semantic_matcher.py` - Semantic label matching

---

## Manual Steps for Each Consumer Repo

### Label Creation Script

Run this `gh` command sequence for each consumer repo:

```bash
REPO="stranske/Travel-Plan-Permission"  # Change for each repo

# Create labels
gh label create "agents:format" \
  --repo "$REPO" \
  --color "0E8A16" \
  --description "Triggers direct issue formatting to AGENT_ISSUE_TEMPLATE" \
  --force

gh label create "agents:formatted" \
  --repo "$REPO" \
  --color "1D76DB" \
  --description "Issue has been formatted to AGENT_ISSUE_TEMPLATE" \
  --force

gh label create "agents:optimize" \
  --repo "$REPO" \
  --color "FBCA04" \
  --description "Triggers issue analysis with optimization suggestions" \
  --force

gh label create "agents:apply-suggestions" \
  --repo "$REPO" \
  --color "0E8A16" \
  --description "Applies optimization suggestions from agents:optimize" \
  --force
```

### Verification Checklist

For each consumer repo after sync:

- [ ] Labels exist and are correctly colored
- [ ] `scripts/langchain/issue_formatter.py` present (Phase 1)
- [ ] Workflow files synced and enabled
- [ ] Test with sample issue
- [ ] Verify LLM fallback works (without API key)

---

## Rollback Procedures

### If Phase 1 Issues Occur

1. Remove `issue_formatter.py` from sync-manifest.yml
2. Trigger sync to remove from consumer repos
3. Document issues in tracking issue

### If Workflow Issues Occur

1. Disable workflow via repository settings
2. Or rename workflow file to `.yml.disabled`
3. Create hotfix PR in Workflows repo

---

## Testing Log

| Date | Repo | Test | Result | Notes |
|------|------|------|--------|-------|
| | | | | |

---

## Notes

- Consumer repos need `OPENAI_API_KEY` secret for full LLM functionality
- Fallback mode uses regex parsing, works without API key
- GitHub Models API uses `GITHUB_TOKEN` automatically (preferred)
