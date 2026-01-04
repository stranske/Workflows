<!-- pr-preamble:start -->
> **Source:** Issue #478

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [x] Create `scripts/langchain/issue_formatter.py` with formatting chain
- [x] Create `ISSUE_FORMATTER_PROMPT` with template rules
- [ ] Add workflow trigger for `agents:format` label
- [ ] Update issue body with formatted version
- [ ] Add `agents:formatted` label on completion
- [x] Add tests for common formatting scenarios

#### Acceptance criteria
- [x] Raw issue body converted to AGENT_ISSUE_TEMPLATE format
- [ ] Tasks are specific, verifiable, iteration-sized (~10 min each)
- [ ] Bullets only used for actual actionable items
- [ ] `agents:format` → `agents:formatted` label transition works
- [x] File paths extracted and included when mentioned

<!-- auto-status-summary:end -->
