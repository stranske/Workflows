# LangChain Issue Intake Enhancement Proposal

> **Status**: Proposal
> **Created**: 2026-01-03
> **Related**: [langchain-keepalive-integration.md](./langchain-keepalive-integration.md)
> **Target Workflows**: `agents-63-issue-intake.yml`, `reusable-agents-issue-bridge.yml`

---

## Executive Summary

This proposal explores how LangChain can enhance the Agents 63 issue intake pipeline to improve issue quality, reduce wasted agent iterations, and provide better human-agent collaboration. We focus on **high-probability, scoped improvements** rather than speculative features.

---

## Current Architecture

```
Human describes problem → Manual formatting → Issue labeled → agents-63-issue-intake.yml
                                                                      ↓
                                                   reusable-agents-issue-bridge.yml
                                                                      ↓
                                              Creates PR with agent:codex + agents:keepalive
                                                                      ↓
                                              Keepalive loop runs until tasks complete (or stuck)
```

**Pain Points Identified:**
1. Manual formatting into AGENT_ISSUE_TEMPLATE is tedious and error-prone
2. Tasks/criteria that agents can't address waste iterations
3. No pre-flight validation catches problems before agent engagement
4. Human-agent iteration for issue refinement is clunky

---

## Proposed Enhancements

### 1. Human Language → AGENT_ISSUE_TEMPLATE Conversion

**Use Case**: User describes a problem in natural language, LLM structures it into the canonical format.

**Technical Approach**:
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

ISSUE_FORMATTER_PROMPT = """
You are an expert at formatting GitHub issues for the Codex agent pipeline.

Convert this human description into the AGENT_ISSUE_TEMPLATE format:

{human_description}

Required sections:
- ## Why - Motivation and context
- ## Scope - What this issue covers
- ## Non-Goals - What is explicitly excluded
- ## Tasks - Actionable checklist items (ONLY use bullets for actual work items)
- ## Acceptance Criteria - Verifiable completion conditions
- ## Implementation Notes - Technical guidance (optional)

CRITICAL RULES:
1. Tasks must be specific, verifiable, and completable by an agent
2. Each task should be small enough for one iteration (~10 minutes)
3. DO NOT include bullets for instructions or notes - only actionable items
4. Acceptance criteria must be objectively verifiable
5. Include relevant file paths if mentioned

Output the formatted issue in Markdown.
"""

llm = ChatOpenAI(
    model="gpt-4o-mini",
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
)

chain = ChatPromptTemplate.from_template(ISSUE_FORMATTER_PROMPT) | llm
```

**Trigger Mechanism**: 
- Label `agents:format` on a raw issue
- Workflow parses issue body, calls LLM, updates issue with formatted version
- Adds `agents:formatted` label and removes `agents:format`

**Plausibility**: ⭐⭐⭐⭐ HIGH
- Simple prompt engineering, proven pattern
- Single LLM call, fast feedback
- Clear input/output contract

**Scope**: ~2-3 days development
- Add formatting chain to `scripts/` (Python, LangChain)
- Add workflow step to `agents-63-issue-intake.yml`
- Tests for common formatting scenarios

---

### 2. Contextual Data Injection for PRs

**Use Case**: Add relevant context to PRs that doesn't fit Tasks/Acceptance (e.g., related issues, design decisions, constraints).

**Technical Approach**:
```python
CONTEXT_EXTRACTOR_PROMPT = """
From this issue and related discussion, extract:
1. Design constraints or decisions made
2. Related issues/PRs that provide context
3. External references (docs, APIs, specifications)
4. Known blockers or dependencies

Format as a "## Context for Agent" section that provides helpful background
without creating actionable tasks.
"""
```

**Integration Point**:
- Run during PR creation in `reusable-agents-issue-bridge.yml`
- Insert extracted context into PR body after Scope but before Tasks
- Preserves in `<!-- context:start -->...<!-- context:end -->` markers

**Plausibility**: ⭐⭐⭐ MEDIUM-HIGH
- Straightforward extraction task
- Value depends on issue quality
- May produce low-signal output for sparse issues

**Scope**: ~1-2 days
- Add context extraction chain
- Modify `agents_pr_meta_update_body.js` to include context section
- Optional: fetch linked issue comments for richer context

---

### 3. Agent Capability Pre-Flight Check (HIGH VALUE)

**Use Case**: Before engaging the keepalive pipeline, validate that tasks are actionable by the agent.

**The Problem**:
Agents waste iterations on tasks they fundamentally cannot complete:

| Task Type | Agent Capability | Example |
|-----------|------------------|---------|
| Code changes | ✅ CAN DO | "Add unit tests for X" |
| CI must pass | ⚠️ PARTIAL | Can fix code, cannot retry CI |
| Workflow files | ❌ CANNOT DO | "Update CI workflow" (protected) |
| Repo settings | ❌ CANNOT DO | "Enable branch protection" |
| External services | ❌ CANNOT DO | "Configure AWS credentials" |
| Human decisions | ❌ CANNOT DO | "Decide on API design" |
| Coverage targets | ⚠️ PARTIAL | Can add tests, cannot guarantee % |

**Technical Approach**:
```python
AGENT_CAPABILITY_CHECK_PROMPT = """
Analyze these tasks and acceptance criteria for agent compatibility.

Tasks:
{tasks}

Acceptance Criteria:
{acceptance}

For each item, classify as:
- ACTIONABLE: Agent can directly complete this
- PARTIAL: Agent can contribute but may not fully satisfy
- BLOCKED: Agent cannot complete this (explain why)

Known agent limitations:
- Cannot modify protected workflow files (.github/workflows/*.yml)
- Cannot change repository settings (branch protection, secrets, etc.)
- Cannot interact with external services requiring credentials
- Cannot make subjective design decisions requiring human input
- Cannot guarantee specific coverage percentages (can add tests, coverage varies)
- Cannot retry CI/CD pipelines - only fix code and push

Output JSON:
{
  "actionable_tasks": [...],
  "partial_tasks": [{"task": "...", "limitation": "..."}],
  "blocked_tasks": [{"task": "...", "reason": "...", "suggested_action": "..."}],
  "recommendation": "PROCEED|REVIEW_NEEDED|BLOCKED",
  "human_actions_needed": [...]
}
"""
```

**Integration Points**:
1. **Pre-bridge check** (`agents-63-issue-intake.yml`):
   - Before creating PR, run capability check
   - If BLOCKED tasks exist, comment on issue with summary
   - Add `agents:review-needed` label instead of `agent:codex`

2. **Task filtering** (`reusable-agents-issue-bridge.yml`):
   - Move blocked tasks to "## Deferred Tasks (Requires Human)" section
   - Keep only actionable tasks in main Tasks section
   - Preserve blocked items for visibility without burning agent iterations

3. **Summary comment**:
   - Post comment explaining: "X tasks are agent-compatible, Y tasks require human action"
   - Include specific guidance for human actions

**Plausibility**: ⭐⭐⭐⭐⭐ VERY HIGH
- Directly addresses #1 pain point (wasted iterations)
- Clear, objective criteria for classification
- High signal-to-noise ratio in output

**Scope**: ~3-4 days
- Capability classification chain + tests
- Workflow integration with label handling
- Comment formatter for human guidance
- Update `issue_scope_parser.js` to handle deferred section

---

### 4. Analyze → Approve → Format (Hybrid Issue Optimization)

**Use Case**: Human labels issue with `agents:optimize` to get LLM suggestions, reviews them, then approves application via a second label.

**Design Philosophy**: Eliminates complex stateful conversation in favor of a simple two-phase flow that reuses the Formatter (#1).

**Flow**:
```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: Analysis (label: agents:optimize)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Human labels issue with `agents:optimize`                       │
│                          ↓                                       │
│  LLM analyzes issue and posts comment:                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ## Issue Optimization Suggestions                          │ │
│  │                                                            │ │
│  │ **Tasks:**                                                 │ │
│  │ - ⚠️ Task 3 is too broad - split into: X, Y, Z            │ │
│  │ - ❌ Task 5 requires workflow changes (agent can't do)     │ │
│  │                                                            │ │
│  │ **Acceptance Criteria:**                                   │ │
│  │ - ⚠️ "Code is clean" is subjective → suggest "ruff passes" │ │
│  │                                                            │ │
│  │ **Missing:**                                               │ │
│  │ - No file paths mentioned                                  │ │
│  │ - Scope section is empty                                   │ │
│  │                                                            │ │
│  │ **To apply:** Add label `agents:apply-suggestions`         │ │
│  │ **To reject:** Remove `agents:optimize` label              │ │
│  │ <!-- suggestions-json: {...} -->                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    Human reviews suggestions
                    (can ask questions in comments - LLM responds informatively)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Phase 2: Approval (label: agents:apply-suggestions)             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  System detects approval label                                   │
│                          ↓                                       │
│  Extracts suggestions from comment JSON                          │
│                          ↓                                       │
│  Routes to Formatter (#1) with:                                  │
│    - Original issue body                                         │
│    - Approved suggestions                                        │
│    - Instruction: "Apply these improvements"                     │
│                          ↓                                       │
│  Formatter produces optimized issue body                         │
│                          ↓                                       │
│  Updates issue + removes both labels + adds `agents:formatted`   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why This Works Better Than Multi-Turn Conversation**:

| Aspect | Original Approach | Hybrid Approach |
|--------|-------------------|-----------------|
| State management | LangGraph state machine across runs | Stateless - suggestions in comment JSON |
| Human approval | Implicit in conversation ("apply") | Explicit label = clear signal |
| Implementation | Custom conversation handler | Reuses Formatter (#1) |
| Complexity | 5-7 days | **2-3 days** |
| Human questions | Must track conversation state | Free-form - no state needed |

**Technical Approach**:
```python
# Phase 1: Analyzer
ANALYZE_ISSUE_PROMPT = """
Analyze this issue for agent compatibility and formatting quality.

Issue body:
{issue_body}

Identify:
1. Tasks that are too broad (should be split)
2. Tasks the agent cannot complete (with reasons from AGENT_LIMITATIONS)
3. Subjective acceptance criteria (suggest objective alternatives)
4. Missing sections (scope, implementation notes, file paths)
5. Formatting issues (bullets used for non-tasks, etc.)

AGENT_LIMITATIONS:
- Cannot modify .github/workflows/*.yml (protected)
- Cannot change repository settings
- Cannot guarantee specific coverage percentages
- Cannot make subjective design decisions
- Cannot retry CI pipelines

Output JSON with structured suggestions.
"""

# Phase 2: Apply - calls Formatter (#1) with suggestions context
APPLY_SUGGESTIONS_PROMPT = """
Reformat this issue applying the approved suggestions.

Original issue:
{original_body}

Approved suggestions:
{suggestions_json}

Apply ALL suggestions and output the complete reformatted issue
following AGENT_ISSUE_TEMPLATE structure. Move blocked tasks to
a "## Deferred Tasks (Requires Human)" section.
"""
```

**Workflow Integration**:
```yaml
# In agents-63-issue-intake.yml

# Triggered by: labeled with agents:optimize
analyze_for_optimization:
  if: github.event.action == 'labeled' && github.event.label.name == 'agents:optimize'
  steps:
    - name: Analyze issue and post suggestions
      uses: actions/github-script@v7
      with:
        script: |
          const { analyzeIssue } = require('./scripts/langchain/issue_optimizer.py');
          const suggestions = await analyzeIssue({
            issueBody: context.payload.issue.body,
            issueNumber: context.payload.issue.number
          });
          // Post comment with suggestions + embedded JSON
          
# Triggered by: labeled with agents:apply-suggestions  
apply_optimization:
  if: github.event.action == 'labeled' && github.event.label.name == 'agents:apply-suggestions'
  steps:
    - name: Extract suggestions from analysis comment
      id: extract
      # Find comment with <!-- suggestions-json: --> marker
      
    - name: Route to formatter with suggestions
      # Calls Formatter (#1) with original body + suggestions
      
    - name: Update issue body
    - name: Clean up labels (remove optimize, apply-suggestions; add formatted)
```

**Human Questions Are Free**:
If human comments with a question after Phase 1, an optional responder job can:
- Answer informatively about the suggestions
- NOT update any state
- NOT require approval tracking

This keeps the complexity low while allowing natural interaction.

**Plausibility**: ⭐⭐⭐⭐ HIGH
- Stateless design eliminates complexity
- Reuses Formatter (#1) infrastructure
- Clear approval signal via label
- No conversation state to manage

**Scope**: ~2-3 days
- Issue analyzer chain (new)
- Suggestion comment formatter
- Apply job that extracts JSON and calls Formatter
- Label management

---

## Additional High-Value Enhancements

### 5. Post-Merge Learning Feedback

**Use Case**: After PR merges, capture what worked/didn't for future issue formatting.

**Approach**:
- Track: iterations used, tasks completed vs. stuck, human interventions
- Feed back into formatting prompts: "Issues like X typically need Y structure"
- Build corpus of successful issue patterns

**Plausibility**: ⭐⭐⭐ MEDIUM-HIGH
**Scope**: ~2-3 days (data collection), ongoing refinement

### 6. Duplicate/Related Issue Detection

**Use Case**: Before creating new issue, check if similar work exists.

**Approach**:
- Embed issue description, compare to existing open issues
- Warn if high similarity detected
- Link related issues for context

**Plausibility**: ⭐⭐⭐⭐ HIGH (embeddings are well-understood)
**Scope**: ~2 days

### 7. Automatic Task Decomposition

**Use Case**: Large tasks get automatically split into smaller, iteration-sized pieces.

**Approach**:
```python
TASK_DECOMPOSITION_PROMPT = """
This task is too large for a single agent iteration (~10 minutes):

{large_task}

Decompose into smaller, independently verifiable sub-tasks.
Each sub-task should:
- Be completable in one iteration
- Have a clear verification condition
- Not depend on un-merged work from other sub-tasks
"""
```

**Plausibility**: ⭐⭐⭐ MEDIUM-HIGH
**Scope**: ~1-2 days

---

## Implementation Priority Matrix

| Enhancement | Value | Effort | Priority |
|-------------|-------|--------|----------|
| 3. Agent Capability Pre-Flight | ⭐⭐⭐⭐⭐ | 3-4d | **P0 - Do First** |
| 1. Human → Template Conversion | ⭐⭐⭐⭐ | 2-3d | **P1** |
| 4. Analyze → Approve → Format | ⭐⭐⭐⭐ | 2-3d | **P1** (reuses #1) |
| 7. Task Decomposition | ⭐⭐⭐ | 1-2d | **P2** |
| 6. Duplicate Detection | ⭐⭐⭐⭐ | 2d | **P2** |
| 2. Context Injection | ⭐⭐⭐ | 1-2d | **P2** |
| 5. Learning Feedback | ⭐⭐⭐ | 2-3d | **P3** |

**Note**: #4 moved from P3 to P1 because the hybrid design reuses #1's Formatter infrastructure and eliminates state management complexity.

---

## Technical Architecture

### Shared Infrastructure

```
scripts/
  langchain/
    __init__.py
    llm_factory.py         # GitHub Models + fallback providers
    issue_formatter.py     # Human → template conversion (#1)
    issue_optimizer.py     # Analyze + apply suggestions (#4)
    capability_check.py    # Agent limitation analysis (#3)
    task_decomposer.py     # Large task splitting (#7)
    prompts/
      format_issue.md
      analyze_issue.md
      apply_suggestions.md
      check_capability.md
      decompose_task.md
```

### Component Relationships

```
                    ┌─────────────────────┐
                    │   llm_factory.py    │
                    │  (GitHub Models +   │
                    │   fallback chain)   │
                    └─────────┬───────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ capability_   │   │ issue_          │   │ issue_          │
│ check.py (#3) │   │ formatter.py(#1)│◄──│ optimizer.py(#4)│
│               │   │                 │   │                 │
│ Pre-flight    │   │ Raw text →      │   │ Phase 1: Analyze│
│ validation    │   │ Template format │   │ Phase 2: Apply  │
└───────────────┘   └─────────────────┘   │ (calls #1)      │
                                          └─────────────────┘
```

### Workflow Integration Points

```yaml
# agents-63-issue-intake.yml additions

jobs:
  # NEW: Optimize flow (Phase 1)
  analyze_for_optimization:
    if: github.event.action == 'labeled' && github.event.label.name == 'agents:optimize'
    steps:
      - name: Analyze issue
        # Posts suggestion comment with embedded JSON
        
  # NEW: Optimize flow (Phase 2)  
  apply_optimization:
    if: github.event.action == 'labeled' && github.event.label.name == 'agents:apply-suggestions'
    steps:
      - name: Extract suggestions from comment
      - name: Route to formatter with suggestions
      - name: Update issue body
      - name: Clean up labels

  # NEW: Format flow
  format_issue:
    if: github.event.action == 'labeled' && github.event.label.name == 'agents:format'
    steps:
      - name: Format raw issue into template
      - name: Update issue body
      - name: Swap labels (format → formatted)

  # EXISTING: Pre-flight check before bridge
  preprocess:
    name: LLM Pre-processing
    steps:
      - name: Check agent capability
        id: capability
        uses: actions/github-script@v7
        with:
          script: |
            const { checkAgentCapability } = require('./scripts/langchain/capability_check.py');
            const result = await checkAgentCapability({
              tasks: '${{ steps.parse.outputs.tasks }}',
              acceptance: '${{ steps.parse.outputs.acceptance }}'
            });
            core.setOutput('recommendation', result.recommendation);
            core.setOutput('blocked_tasks', JSON.stringify(result.blocked_tasks));
            
      - name: Post capability summary
        if: steps.capability.outputs.recommendation != 'PROCEED'
        uses: actions/github-script@v7
        with:
          script: |
            // Post comment with blocked task analysis
            // Add agents:review-needed label
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| LLM produces poor formatting | Template validation + human review before agent engagement |
| False positives in capability check | Conservative defaults (flag uncertain items for review) |
| API rate limits | Use existing GitHub Models quota, add exponential backoff |
| Increased workflow complexity | Modular design, feature flags for gradual rollout |
| LLM hallucinations in task decomposition | Preserve original task, show decomposition as suggestions |

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Agent iterations per PR | ~5 avg | ~3 avg | Keepalive metrics |
| PRs stuck on blocked tasks | ~20% | <5% | Track `agents:review-needed` vs successful merges |
| Issue formatting time | ~15 min | ~2 min | User survey |
| False positive blocked tasks | N/A | <10% | Manual review sample |

---

## Next Steps

1. **Proof of Concept**: Implement capability check (#3) as standalone script
2. **Validate**: Run against 10 recent issues, measure accuracy
3. **Integrate**: Add to `agents-63-issue-intake.yml` behind feature flag
4. **Iterate**: Refine prompts based on real-world results
5. **Expand**: Add human→template conversion (#1) using same infrastructure

---

## Appendix: Known Agent Limitations Reference

For inclusion in capability check prompts:

```
AGENT CANNOT:
- Modify workflow files in .github/workflows/ (protected by agents-guard)
- Change repository settings (branch protection, secrets, webhooks)
- Access external services requiring credentials not in environment
- Run commands requiring interactive input
- Make subjective design decisions (API design, architecture choices)
- Guarantee specific test coverage percentages
- Retry CI pipelines - can only fix code and push

AGENT CAN (with limitations):
- Add tests (but coverage depends on test quality)
- Fix lint/format issues (but may introduce new ones)
- Update documentation (but may not match current state)
- Refactor code (but large refactors may exceed iteration time)

AGENT CAN FULLY:
- Add/modify Python/JS/YAML files (except protected workflows)
- Create new test files
- Update configuration files
- Add type hints and docstrings
- Fix specific identified bugs
```
