<!-- pr-preamble:start -->
> **Source:** Issue #477

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [ ] Create `scripts/langchain/capability_check.py` with classification chain
- [ ] Create `AGENT_CAPABILITY_CHECK_PROMPT` with known limitations
- [ ] Add pre-bridge check in `agents-63-issue-intake.yml`
- [ ] Add `agents:review-needed` label handling for blocked tasks
- [ ] Create comment formatter for human guidance summary
- [ ] Update `issue_scope_parser.js` to handle deferred section
- [ ] Add tests for capability classification

#### Acceptance criteria
- [ ] Tasks classified as ACTIONABLE/PARTIAL/BLOCKED with JSON output
- [ ] Blocked tasks trigger `agents:review-needed` label instead of `agent:codex`
- [ ] Comment posted explaining human actions needed
- [ ] Deferred tasks moved to separate section (not sent to agent)

<!-- auto-status-summary:end -->
