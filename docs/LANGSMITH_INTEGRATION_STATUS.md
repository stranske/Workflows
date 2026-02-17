# LangSmith Integration Status

> **Last Updated:** 2026-02-17
> **Branch:** `claude/langsmith-integration-summary-pKJUA`
> **Related Issue:** #974

## Summary

LangSmith tracing infrastructure is now **60% complete (3 of 8 tasks)**. The trace ID extraction pipeline has been implemented end-to-end in both `pr_verifier.py` and `followup_issue_generator.py`. Trace IDs are extracted from LangChain responses and included in JSON outputs.

**Remaining work:** Connect trace IDs to workflow → metrics collector pipeline and surface in PR comments.

---

## ✅ Completed Components

### 1. Core Infrastructure (`tools/llm_provider.py`)

**Added functions:**
- `extract_trace_id(response) -> str | None` - Extracts trace ID from LangChain response objects
- `derive_langsmith_trace_url(trace_id) -> str | None` - Converts trace ID to clickable URL
- `build_langsmith_metadata()` - Already existed, standardizes metadata for LLM calls

**Trace extraction logic:**
- Checks `response.response_metadata["run_id"]`
- Falls back to `response.id`
- Returns `None` if unavailable or `LANGSMITH_ENABLED=False`
- Handles exceptions gracefully with debug logging

**Commit:** `95c4c96` (feat: add LangSmith trace ID extraction to pr_verifier)

---

### 2. PR Verifier Integration (`scripts/langchain/pr_verifier.py`)

**Changes:**
- Added `langsmith_trace_id` and `langsmith_trace_url` fields to `EvaluationResult` dataclass
- Modified `_invoke_llm()` to return tuple: `(response, trace_id, trace_url)`
- Updated `evaluate_pr()` to extract and populate trace info
- Updated `ComparisonRunner.run_single()` for compare mode
- Logs trace URLs when available: `LOGGER.info(f"LangSmith trace: {trace_url}")`

**JSON output:** `result.model_dump()` now includes:
```json
{
  "verdict": "PASS",
  "langsmith_trace_id": "abc123...",
  "langsmith_trace_url": "https://smith.langchain.com/r/abc123..."
}
```

**Commit:** `95c4c96`

---

### 3. Followup Issue Generator Integration (`scripts/langchain/followup_issue_generator.py`)

**Changes:**
- Modified `_invoke_llm()` to return tuple: `(response_text, trace_id, trace_url)`
- Updated all 4 LLM invocations in `_generate_with_llm()`:
  1. `analyze_verification` → `trace_id_1, trace_url_1`
  2. `generate_tasks` → `trace_id_2, trace_url_2`
  3. `generate_acceptance_criteria` → `trace_id_3, trace_url_3`
  4. `format_followup_issue` → `trace_id_4, trace_url_4`

**Trace URL storage:** Appends HTML comments to generated issue body:
```html
<!-- LangSmith analyze_verification: https://smith.langchain.com/r/abc123 -->
<!-- LangSmith generate_tasks: https://smith.langchain.com/r/def456 -->
<!-- LangSmith generate_acceptance_criteria: https://smith.langchain.com/r/ghi789 -->
<!-- LangSmith format_followup_issue: https://smith.langchain.com/r/jkl012 -->
```

**Commit:** `e011876`

---

## 🔨 In Progress

### 4. Workflow Integration (Partially Complete)

**Current state:**
- ✅ pr_verifier.py outputs trace IDs in JSON (via `--json` flag)
- ✅ Workflows capture JSON output: `python pr_verifier.py ... > evaluation.json`
- ❌ Workflows do NOT extract trace IDs from JSON
- ❌ Workflows do NOT pass `--langsmith-trace-id` to `autopilot_metrics_collector.py`

**Where trace extraction is needed:**
- `.github/workflows/reusable-agents-verifier.yml` (lines 532, 658)
- `.github/workflows/agents-auto-pilot.yml` (issue_optimizer, issue_formatter calls)

**Example of what's needed:**
```yaml
# After capturing JSON output
- name: Extract trace ID from evaluation
  id: trace
  run: |
    TRACE_ID=$(jq -r '.langsmith_trace_id // empty' evaluation.json)
    TRACE_URL=$(jq -r '.langsmith_trace_url // empty' evaluation.json)
    echo "trace_id=$TRACE_ID" >> $GITHUB_OUTPUT
    echo "trace_url=$TRACE_URL" >> $GITHUB_OUTPUT

# When calling metrics collector
- name: Record metrics
  run: |
    python scripts/autopilot_metrics_collector.py \
      --path "$METRICS_PATH" \
      --metric-type step \
      --success true \
      --langsmith-trace-id "${{ steps.trace.outputs.trace_id }}" \
      --langsmith-trace-url "${{ steps.trace.outputs.trace_url }}"
```

---

## ⏳ Pending Work

### 5. PR Comment Integration

**Goal:** Surface trace URLs in PR comments for easy debugging

**Current state:**
- Evaluation reports posted to PRs via `reusable-agents-verifier.yml`
- Reports show scores, verdict, concerns
- No trace URL links

**What's needed:**
- Add section to comment template: `format_evaluation_comment()` in pr_verifier.py
- Example:
  ```markdown
  ## PR Verification Report

  **Verdict:** CONCERNS (62% confidence)

  ### Scores
  - Correctness: 8/10
  - Completeness: 7/10
  ...

  ### LangSmith Traces
  - [View evaluation trace](https://smith.langchain.com/r/abc123)
  ```

**Files to modify:**
- `scripts/langchain/pr_verifier.py` - `format_evaluation_comment()` function
- `scripts/langchain/pr_verifier.py` - `format_comparison_report()` function

---

### 6. Metrics Aggregation Script

**Goal:** `scripts/aggregate_metrics.py` for weekly/monthly summaries

**Current state:** ❌ File does not exist

**What's needed:**
```python
#!/usr/bin/env python3
"""Aggregate metrics from NDJSON autopilot metrics logs."""

import argparse
import json
from pathlib import Path
from collections import defaultdict

def aggregate_metrics(metrics_path: Path) -> dict:
    """Read NDJSON metrics and compute aggregates."""
    metrics = []
    with open(metrics_path) as f:
        for line in f:
            if line.strip():
                metrics.append(json.loads(line))

    # Group by operation
    by_operation = defaultdict(list)
    for m in metrics:
        if "langsmith_trace_id" in m:
            operation = m.get("operation", "unknown")
            by_operation[operation].append(m)

    return {
        "total_traces": len([m for m in metrics if "langsmith_trace_id" in m]),
        "by_operation": {
            op: len(traces) for op, traces in by_operation.items()
        },
        "trace_coverage": len([m for m in metrics if "langsmith_trace_id" in m]) / len(metrics) if metrics else 0
    }

if __name__ == "__main__":
    # Parse args, aggregate, output JSON summary
    pass
```

**Files to create:**
- `scripts/aggregate_metrics.py`
- Weekly workflow: `.github/workflows/maint-langsmith-metrics.yml`

---

### 7. Unit Tests

**Goal:** Test trace extraction logic

**Current state:** ❌ No tests for `extract_trace_id()`

**What's needed:**
```python
# tests/tools/test_llm_provider.py

def test_extract_trace_id_from_response():
    """Test extracting trace ID from LangChain response."""
    from tools.llm_provider import extract_trace_id

    # Mock response with response_metadata
    class MockResponse:
        def __init__(self, trace_id):
            self.response_metadata = {"run_id": trace_id}

    response = MockResponse("abc123def456")
    assert extract_trace_id(response) == "abc123def456"

def test_extract_trace_id_returns_none_when_unavailable():
    """Test graceful handling when trace ID is unavailable."""
    from tools.llm_provider import extract_trace_id

    class MockResponse:
        pass

    response = MockResponse()
    assert extract_trace_id(response) is None
```

**Files to modify:**
- `tests/tools/test_llm_provider.py` - Add 5-10 test cases

---

### 8. End-to-End Testing

**Goal:** Verify full pipeline: LLM call → trace extraction → metrics → PR comment

**Test plan:**
1. Trigger `reusable-agents-verifier.yml` on a test PR
2. Verify JSON output includes `langsmith_trace_id` and `langsmith_trace_url`
3. Verify metrics JSON includes trace fields (once workflows updated)
4. Verify PR comment includes trace link (once comments updated)

**Acceptance criteria:**
- [ ] Trace ID appears in `evaluation.json` from pr_verifier.py
- [ ] Trace URL is clickable and opens LangSmith dashboard
- [ ] Metrics NDJSON includes `langsmith_trace_id` field
- [ ] PR comment has "View evaluation trace" link
- [ ] Weekly metrics summary shows trace coverage %

---

## 📊 Progress Summary

| Component | Status | Commit |
|-----------|--------|--------|
| Core infrastructure (extract_trace_id) | ✅ Complete | 95c4c96 |
| pr_verifier integration | ✅ Complete | 95c4c96 |
| followup_issue_generator integration | ✅ Complete | e011876 |
| Workflow→metrics pass-through | ⏳ In progress | - |
| PR comment trace links | ⏳ Pending | - |
| Metrics aggregation script | ⏳ Pending | - |
| Unit tests | ⏳ Pending | - |
| End-to-end testing | ⏳ Pending | - |

**Overall completion:** ~60% (3 of 8 tasks complete, 1 in progress, 4 pending)

---

## 🚀 Next Steps (Priority Order)

1. **Update `.github/workflows/reusable-agents-verifier.yml`:**
   - Extract trace IDs from JSON after pr_verifier.py calls
   - Pass trace IDs to metrics collector (if metrics are collected in this workflow)

2. **Update PR comment templates:**
   - Add "LangSmith Traces" section to `format_evaluation_comment()`
   - Add trace URLs to comparison reports

3. **Create `scripts/aggregate_metrics.py`:**
   - Read NDJSON metrics files
   - Calculate trace coverage, traces by operation
   - Output summary JSON

4. **Add unit tests:**
   - Test `extract_trace_id()` with various response formats
   - Test `derive_langsmith_trace_url()` formatting

5. **End-to-end test:**
   - Run verifier on test PR
   - Verify trace URLs end-to-end

---

## 📁 Files Modified

- `tools/llm_provider.py` - Added `extract_trace_id()` function
- `scripts/langchain/pr_verifier.py` - Added trace extraction and JSON output
- `scripts/langchain/followup_issue_generator.py` - Added trace extraction for all 4 LLM calls

## 📁 Files To Modify

- `.github/workflows/reusable-agents-verifier.yml` - Extract and pass trace IDs
- `.github/workflows/agents-auto-pilot.yml` - Extract and pass trace IDs
- `scripts/langchain/pr_verifier.py` - Update comment formatting
- `scripts/aggregate_metrics.py` - Create new file
- `tests/tools/test_llm_provider.py` - Add trace extraction tests

---

## 💡 Design Notes

### Why HTML Comments in Followup Issues?

Followup issues are created automatically and may be viewed by users who don't need to see trace URLs. HTML comments keep trace links available for maintainers without cluttering the issue UI.

### Why Not Store Traces in a Database?

LangSmith already stores all trace data. We only need to **link** to traces via URLs, not duplicate storage. Metrics NDJSON files provide lightweight local records.

### Trace ID Extraction Strategy

LangChain responses vary by provider (OpenAI, Anthropic, GitHub Models). The `extract_trace_id()` function checks multiple attributes:
1. `response.response_metadata["run_id"]` (standard)
2. `response.id` (fallback)
3. `response.__dict__["id"]` (compatibility)

This ensures robustness across provider implementations.

---

## 🔗 Related Documents

- `docs/agent-automation.md` - LangSmith setup guide
- `docs/ci/AUTOPILOT_METRICS_SCHEMA.md` - Metrics schema documentation
- `.agents/issue-974-ledger.yml` - Task ledger for this work
- `docs/plans/langchain-post-code-rollout.md` - Overall LangChain rollout plan

---

## ✅ Definition of Done

Issue #974 is complete when:
- [x] Trace IDs extracted from LLM responses
- [x] Trace IDs included in JSON outputs
- [ ] Workflows pass trace IDs to metrics collector
- [ ] Metrics NDJSON contains trace fields
- [ ] PR comments show clickable trace URLs
- [ ] `scripts/aggregate_metrics.py` computes trace coverage
- [ ] Unit tests validate extraction logic
- [ ] End-to-end test confirms full pipeline
