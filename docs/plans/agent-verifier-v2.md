# Agent Verifier v2 - LLM-Powered Evaluation

## Overview

Redesign the Agent Verifier workflow to provide more meaningful post-merge evaluation with:
1. **Label-triggered checkbox mode** (opt-in after merge)
2. **LLM-powered independent evaluation mode** (new capability)
3. **Model/provider selection** for evaluation flexibility
4. **Provider comparison mode** to compare evaluations across models

## Relationship to Keepalive LLM Analysis

This design **reuses the same LLM infrastructure** built for keepalive task analysis:

| Component | Keepalive | Verifier | Shared? |
|-----------|-----------|----------|---------|
| Provider framework | `tools/llm_provider.py` | `tools/llm_provider.py` | ✅ Same |
| Provider chain | GitHub Models → OpenAI → Regex | GitHub Models → OpenAI | ✅ Same providers |
| Force provider | `--provider openai` | `--provider openai` | ✅ Same mechanism |
| Structured output | `CompletionAnalysis` | `EvaluationResult` | Similar pattern |
| Confidence scoring | 0-1 scale | 0-1 scale | ✅ Same approach |

**Key reuse:**
```python
# Existing infrastructure we'll reuse
from tools.llm_provider import get_llm_provider, check_providers

# Force a specific provider (already implemented!)
provider = get_llm_provider(force_provider="openai")

# Check what's available
available = check_providers()
# {'github-models': True, 'openai': True, 'regex-fallback': True}
```

## Current State Analysis

### What Exists Today

The current `agents-verifier.yml` workflow:

```
Trigger: pull_request:closed (automatic on every merge)
         ↓
Wait for CI completion (5min timeout)
         ↓
Build verifier context (PR body, linked issues, CI results)
         ↓
Run Codex with verifier_acceptance_check.md prompt
         ↓
Parse verdict (PASS/FAIL based on regex)
         ↓
If FAIL → Create follow-up issue
         ↓
Collect and upload metrics
```

**Current Limitations:**

1. **Automatic execution** - Runs on every merge, even when not needed
2. **Checkbox-focused** - Only checks if acceptance criteria checkboxes are satisfied
3. **No independent evaluation** - Relies on Codex to verify claims, not evaluate quality
4. **Single model** - Hardcoded to use Codex (ChatGPT subscription)
5. **No code analysis** - Doesn't examine the actual diff or implementation
6. **No model comparison** - Can't compare evaluations from different models

---

## Proposed Design

### Modes of Operation

| Mode | Trigger | Purpose | Output |
|------|---------|---------|--------|
| **Checkbox Verification** | Label `verify:checkbox` on merged PR | Verify acceptance criteria checkboxes are accurately marked | Issue if gaps found |
| **LLM Evaluation** | Label `verify:evaluate` on merged PR | Independent quality/correctness evaluation | Evaluation report + optional issue |
| **Model Comparison** | Label `verify:compare` on merged PR | Run evaluation with multiple models | Comparison report |

### Trigger Mechanism

```yaml
on:
  pull_request:
    types: [labeled]  # Only when label added
    
jobs:
  verifier:
    if: |
      github.event.pull_request.merged == true &&
      contains(fromJSON('["verify:checkbox", "verify:evaluate", "verify:compare"]'), github.event.label.name)
```

**Benefits:**
- No automatic execution on every merge
- Explicit opt-in via label
- Can be triggered post-merge by maintainers
- Supports workflow re-runs via label toggle

### Mode 1: Checkbox Verification (Existing, Refined)

**Trigger:** `verify:checkbox` label on merged PR

**Process:**
1. Fetch PR body and linked issues
2. Extract acceptance criteria checkboxes
3. Use LLM to verify each checkbox claim against:
   - CI results (test pass/fail)
   - File existence checks
   - Code pattern matching
4. Report discrepancies

**Prompt Template:** (refined from current)
```markdown
# Checkbox Verification

Verify that each checked checkbox in the acceptance criteria 
accurately reflects the implementation state.

## Context
- PR: {pr_url}
- CI Results: {ci_summary}
- Diff Summary: {diff_stats}

## Acceptance Criteria
{criteria_with_checkboxes}

## Instructions
For each criterion:
1. If checked [x]: Verify the claim is accurate
2. If unchecked [ ]: Confirm it's genuinely incomplete
3. Report any discrepancies

Output format:
- Verdict: PASS | FAIL
- Discrepancies: (list any checkbox/reality mismatches)
```

### Mode 2: LLM Evaluation (New)

**Trigger:** `verify:evaluate` label on merged PR

**Process:**
1. Gather comprehensive context:
   - Original issue/task description
   - PR description and discussion
   - Full diff of changes
   - CI results
   - Related code context (files modified + dependencies)
2. Run independent evaluation with selected model
3. Generate evaluation report
4. Optionally create follow-up issue for concerns

**Evaluation Dimensions:**
- **Correctness**: Does the implementation correctly address the task?
- **Completeness**: Are all requirements addressed?
- **Quality**: Code quality, maintainability, best practices
- **Testing**: Adequate test coverage for changes?
- **Side Effects**: Any unintended consequences or breaking changes?

**Prompt Template:**
```markdown
# Independent Implementation Evaluation

You are an expert code reviewer performing a post-merge evaluation.
Your task is to independently assess whether this implementation 
correctly and completely addresses the original requirements.

## Original Task
{issue_body}

## Implementation (PR #{pr_number})
{pr_description}

## Changes Made
{diff_summary}
{key_file_contents}

## CI Results
{ci_summary}

## Evaluation Instructions

Evaluate this implementation across these dimensions:

### 1. Correctness
- Does the code correctly implement the stated requirements?
- Are there logical errors or edge cases missed?

### 2. Completeness  
- Are all requirements from the original task addressed?
- Is anything partially implemented or deferred?

### 3. Code Quality
- Does the code follow project conventions?
- Is it maintainable and well-structured?
- Are there opportunities for improvement?

### 4. Testing
- Is the change adequately tested?
- Do tests cover the key functionality?

### 5. Risks
- Are there potential side effects?
- Breaking changes to existing functionality?
- Security considerations?

## Output Format

```json
{
  "overall_verdict": "PASS" | "CONCERNS" | "FAIL",
  "confidence": 0.0-1.0,
  "dimensions": {
    "correctness": { "score": 1-5, "notes": "..." },
    "completeness": { "score": 1-5, "notes": "..." },
    "quality": { "score": 1-5, "notes": "..." },
    "testing": { "score": 1-5, "notes": "..." },
    "risks": { "score": 1-5, "notes": "..." }
  },
  "highlights": ["positive observations"],
  "concerns": ["issues to address"],
  "recommendations": ["suggested improvements"]
}
```
```

### Mode 3: Model Comparison (New)

**Trigger:** `verify:compare` label on merged PR

**Process:**
1. Run the same evaluation prompt through multiple providers
2. Collect and compare responses
3. Generate comparison report highlighting:
   - Areas of agreement
   - Areas of disagreement
   - Unique insights from each provider
   - Confidence levels per provider

**Example comparison output:**
```markdown
## Provider Comparison Report

### Agreement (Both providers)
- ✅ Correctness: Implementation correctly addresses requirements
- ✅ Tests: Adequate coverage for core functionality

### Disagreement
| Dimension | GitHub Models (GPT-4o) | OpenAI (GPT-4o) |
|-----------|------------------------|-----------------|
| Quality | 4/5 - "Well structured" | 3/5 - "Could use more comments" |
| Risks | Low | Medium - "Edge case in line 42" |

### Unique Insights
- **GitHub Models**: Noted potential performance issue in loop
- **OpenAI**: Suggested alternative algorithm approach
```

---

## Provider Selection (Reusing Existing Infrastructure)

### Already Implemented

We already have provider selection from the keepalive LLM work:

```python
# tools/llm_provider.py - ALREADY EXISTS
def get_llm_provider(force_provider: str | None = None) -> LLMProvider:
    """
    Args:
        force_provider: If set, use only this provider.
            Options: "github-models", "openai", "regex-fallback"
    """
    if force_provider:
        provider_map = {
            "github-models": GitHubModelsProvider,
            "openai": OpenAIProvider,
            "regex-fallback": RegexFallbackProvider,
        }
        return provider_map[force_provider]()
    # ... fallback chain
```

### Workflow Input Configuration

```yaml
inputs:
  provider:
    description: 'LLM provider to use for evaluation'
    required: false
    type: choice
    default: 'auto'
    options:
      - 'auto'           # Use fallback chain (GitHub Models → OpenAI)
      - 'github-models'  # Force GitHub Models
      - 'openai'         # Force OpenAI API
  
  compare_providers:
    description: 'Run comparison across multiple providers'
    required: false
    type: boolean
    default: false
```

### CLI Usage (for testing)

```bash
# Evaluate with specific provider
python scripts/evaluate_pr.py \
  --pr-number 123 \
  --provider openai \
  --output json

# Compare across providers
python scripts/evaluate_pr.py \
  --pr-number 123 \
  --compare github-models,openai \
  --output markdown
```

### Extension for Evaluation

We'll add an `evaluate()` method to existing providers:

```python
# Extend existing LLMProvider base class
class LLMProvider(ABC):
    # Existing method (for keepalive)
    def analyze_completion(self, session_output, tasks, context) -> CompletionAnalysis:
        ...
    
    # NEW method (for verifier)
    def evaluate_implementation(
        self,
        diff: str,
        requirements: str,
        context: str | None = None,
    ) -> EvaluationResult:
        """Evaluate implementation against requirements."""
        ...
```

This means **GitHubModelsProvider and OpenAIProvider get evaluation capability for free** - same authentication, same API calls, just different prompts.

---

## Implementation Plan

### Phase 1: Refactor Trigger Mechanism (2-3 hours)
1. Change trigger from `pull_request:closed` to `pull_request:labeled`
2. Add mode detection based on label (`verify:checkbox`, `verify:evaluate`, `verify:compare`)
3. Add guard condition for merged PRs only
4. Deprecate but keep old workflow for transition period

### Phase 2: Add Evaluation Method to Existing Providers (3-4 hours)
1. Add `evaluate_implementation()` method to `LLMProvider` base class
2. Implement in `GitHubModelsProvider` (reuse existing client)
3. Implement in `OpenAIProvider` (reuse existing client)
4. Add `EvaluationResult` dataclass (similar to `CompletionAnalysis`)
5. Add `--provider` flag to evaluation CLI (same pattern as keepalive)

### Phase 3: Context Building & Prompts (4-5 hours)
1. Create evaluation prompt template
2. Add diff fetching and summarization
3. Improve CI result collection
4. Create unified `EvaluationContext` data structure

### Phase 4: Provider Comparison Mode (3-4 hours)
1. Run evaluation with multiple providers in parallel
2. Implement response comparison logic
3. Create comparison report formatter

### Phase 5: Integration & Testing (3-4 hours)
1. Add tests (reuse test patterns from keepalive)
2. Create `maint-XX-test-verifier.yml` workflow (like `maint-39-test-llm-providers.yml`)
3. Update consumer repo templates
4. Document usage

**Total: ~15-20 hours** (reduced from original ~20-30 hours due to infrastructure reuse)

---

## Workflow Structure

```yaml
name: Agents Verifier v2

on:
  pull_request:
    types: [labeled]

permissions:
  contents: read
  pull-requests: read
  issues: write
  actions: read
  models: read  # For GitHub Models

jobs:
  determine-mode:
    runs-on: ubuntu-latest
    if: github.event.pull_request.merged == true
    outputs:
      mode: ${{ steps.mode.outputs.mode }}
      should_run: ${{ steps.mode.outputs.should_run }}
    steps:
      - id: mode
        run: |
          label="${{ github.event.label.name }}"
          case "$label" in
            verify:checkbox) echo "mode=checkbox" >> "$GITHUB_OUTPUT" ;;
            verify:evaluate) echo "mode=evaluate" >> "$GITHUB_OUTPUT" ;;
            verify:compare)  echo "mode=compare" >> "$GITHUB_OUTPUT" ;;
            *) echo "should_run=false" >> "$GITHUB_OUTPUT"; exit 0 ;;
          esac
          echo "should_run=true" >> "$GITHUB_OUTPUT"

  checkbox-verification:
    needs: determine-mode
    if: needs.determine-mode.outputs.mode == 'checkbox'
    uses: ./.github/workflows/reusable-verifier-checkbox.yml
    secrets: inherit

  llm-evaluation:
    needs: determine-mode  
    if: needs.determine-mode.outputs.mode == 'evaluate'
    uses: ./.github/workflows/reusable-verifier-evaluate.yml
    with:
      model: ${{ inputs.model || 'github-gpt-4o' }}
    secrets: inherit

  model-comparison:
    needs: determine-mode
    if: needs.determine-mode.outputs.mode == 'compare'
    uses: ./.github/workflows/reusable-verifier-compare.yml
    secrets: inherit
```

---

## Suggested Improvements to Original Plan

### 1. Add Confidence Scoring
Each evaluation should include a confidence score (0-1) indicating how certain the model is about its assessment. Low confidence → flag for human review.

### 2. Structured Output Enforcement
Use JSON output format with strict schema validation. This enables:
- Programmatic processing of results
- Consistent reporting across models
- Easier comparison in model comparison mode

### 3. Context Window Management
Large diffs may exceed model context limits. Add:
- Intelligent diff summarization
- Priority-based file selection (most relevant first)
- Chunked evaluation for very large PRs

### 4. Caching and Cost Control
- Cache evaluation results to avoid re-running
- Add cost estimation before running expensive models
- Support dry-run mode to preview what would be evaluated

### 5. Feedback Loop
- Allow humans to mark evaluations as accurate/inaccurate
- Use feedback to improve prompts over time
- Track model accuracy per repository/domain

### 6. Progressive Evaluation
For large changes, consider:
1. Quick triage (fast model, high-level check)
2. Deep evaluation (slower model, detailed analysis)
3. Human review trigger for edge cases

### 7. Integration with Existing Systems
- Link evaluation results to PR timeline
- Add evaluation badges/status checks
- Integrate with project health dashboards

---

## Open Questions

1. **Default behavior**: Should there be an auto-trigger option for certain PR types (e.g., agent-created PRs)?

2. **Model costs**: How to handle cost allocation for expensive models like o1?

3. **Evaluation scope**: Should evaluation include upstream/downstream impact analysis?

4. **Historical comparison**: Compare new implementation against previous versions?

5. **Multi-repo evaluation**: For changes spanning multiple repositories?

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| False positive rate | < 10% | Human review of FAIL verdicts |
| Evaluation accuracy | > 85% | Feedback from maintainers |
| Time to evaluation | < 5 min | Workflow duration |
| Provider agreement | > 70% | Comparison mode analysis |
| Follow-up issue quality | High | Issue resolution rate |

---

## Timeline Estimate (Updated - Leveraging Existing Infrastructure)

| Phase | Effort | Dependencies | Reuse |
|-------|--------|--------------|-------|
| Phase 1: Trigger Refactor | 2-3 hours | None | — |
| Phase 2: Add evaluate() to providers | 3-4 hours | Phase 1 | ✅ Reuse `llm_provider.py` |
| Phase 3: Context & Prompts | 4-5 hours | Phase 2 | ✅ Reuse verifier context.js |
| Phase 4: Provider Comparison | 3-4 hours | Phase 3 | ✅ Reuse `--provider` flag |
| Phase 5: Integration | 3-4 hours | All phases | ✅ Reuse test patterns |

**Total: ~15-20 hours** (reduced due to reusing keepalive LLM infrastructure)

---

## Related Files

### Existing Infrastructure (to reuse)
- [llm_provider.py](../../tools/llm_provider.py) - LLM provider framework with `force_provider` support
- [analyze_codex_session.py](../../scripts/analyze_codex_session.py) - CLI with `--provider` flag
- [maint-39-test-llm-providers.yml](../../.github/workflows/maint-39-test-llm-providers.yml) - Provider test workflow

### Current Verifier (to refactor)
- [agents-verifier.yml](../../.github/workflows/agents-verifier.yml) - Current workflow
- [reusable-agents-verifier.yml](../../.github/workflows/reusable-agents-verifier.yml) - Reusable version
- [verifier_acceptance_check.md](../../.github/codex/prompts/verifier_acceptance_check.md) - Current prompt
- [agents_verifier_context.js](../../.github/scripts/agents_verifier_context.js) - Context builder

### Documentation
- [llm-task-analysis.md](../llm-task-analysis.md) - Keepalive LLM documentation (similar pattern)
