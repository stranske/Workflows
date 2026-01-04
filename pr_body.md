<!-- pr-preamble:start -->
> **Source:** Issue #479

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [ ] Create `scripts/langchain/issue_optimizer.py` with analyzer chain
- [ ] Create `ANALYZE_ISSUE_PROMPT` with agent limitations context
- [ ] Create suggestion comment formatter with embedded JSON
- [ ] Add workflow trigger for `agents:optimize` label (Phase 1)
- [ ] Add workflow trigger for `agents:apply-suggestions` label (Phase 2)
- [ ] Extract suggestions JSON and route to Formatter (#478)
- [ ] Add label management (remove optimize/apply, add formatted)
- [ ] Add tests for analyze and apply phases

#### Acceptance criteria
- [x] `agents:optimize` triggers analysis comment with structured suggestions
- [ ] Suggestions include task splitting, blocked task identification, objective criteria
- [ ] Comment contains `<- Updated WORKFLOW_OUTPUTS.md suggestions-json: {...} -->` marker
- [x] `agents:apply-suggestions` extracts JSON and calls Formatter
- [ ] Issue body updated with applied improvements
- [ ] Labels cleaned up appropriately

<!-- auto-status-summary:end -->
