<!-- pr-preamble:start -->
> **Source:** Issue #482

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

<!-- Updated WORKFLOW_OUTPUTS.md context:start -->
## Context for Agent
- Pending extraction from linked issue context.
<!-- Updated WORKFLOW_OUTPUTS.md context:end -->

#### Tasks
- [x] Create context extraction chain with `CONTEXT_EXTRACTOR_PROMPT`
- [x] Run during PR creation in `reusable-agents-issue-bridge.yml`
- [x] Insert context into PR body after Scope, before Tasks
- [x] Preserve in `<- Updated WORKFLOW_OUTPUTS.md context:start -->...<- Updated WORKFLOW_OUTPUTS.md context:end -->` markers
- [x] Modify `agents_pr_meta_update_body.js` to include context section
- [x] Optional: fetch linked issue comments for richer context
- [x] Add tests for context extraction

#### Acceptance criteria
- [x] Context section added to PR body when relevant
- [x] Related issues/PRs linked
- [x] Design decisions captured
- [x] Markers allow programmatic identification

<!-- auto-status-summary:end -->
