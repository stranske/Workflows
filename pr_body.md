<!-- pr-preamble:start -->
> **Source:** Issue #455

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
The current `issue_scope_parser.js` relies on regex patterns to extract Scope, Tasks, and Acceptance Criteria sections from PR bodies. When markdown formatting varies (different header styles, nested lists, missing sections), extraction fails and keepalive stops with "no-checklists" errors.

#### Tasks
- [x] Audit current `issue_scope_parser.js` for fragile patterns
- [x] Add fallback patterns for common variations:
- [x] - Bold headers (`**Tasks**`) vs markdown headers (`## Tasks`)
- [x] - Numbered lists with checkboxes (`1. [ ] Task`)
- [ ] - Nested task lists
- [ ] - Missing section markers
- [x] Add optional LLM extraction layer (gated by config/env var)
- [x] Port LangChain extraction from `stranske/Trend_Model_Project/tools/langchain_task_extractor.py`
- [x] Add tests for varied markdown formats
- [x] Document supported variations

#### Acceptance criteria
- [x] Extraction succeeds with bold headers (`**Tasks**:`)
- [x] Extraction succeeds with varied heading levels (`### Tasks`, `#### Tasks`)
- [x] Extraction handles nested checkbox lists
- [x] Extraction handles missing optional sections gracefully
- [x] LLM extraction is opt-in and fails gracefully when unavailable
- [x] No regression on currently working formats
- [x] Tests cover at least 5 markdown variations

<!-- auto-status-summary:end -->
