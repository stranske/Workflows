<!-- pr-preamble:start -->
> **Source:** Issue #456

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
Keepalive prompt generation uses hand-rolled templates in `keepalive_instruction_template.js` with string concatenation. This makes it difficult to:
- Route to different prompt strategies based on context (CI failure vs feature work)
- Track what was attempted in previous rounds
- Adapt instructions based on accumulated state

#### Tasks
- [x] Design prompt composition interface
- [x] Implement round-over-round state tracking (what was tried, what failed)
- [ ] Add routing logic for different scenarios:
- [ ] - CI failure: prioritize fix instructions
- [ ] - Feature work: next task selection
- [ ] - Verification: completion checking
- [ ] Integrate with existing `keepalive_state.js` state management
- [ ] Add memory of attempted tasks to avoid repetition
- [ ] Document prompt composition patterns

#### Acceptance criteria
- [x] Prompts can be composed from reusable segments
- [ ] State persists across keepalive rounds within a session
- [ ] CI failures trigger fix-first prompt strategy
- [ ] Previously attempted tasks are tracked and deprioritized
- [x] Prompt generation is testable with mock state
- [ ] No regression in existing keepalive functionality

<!-- auto-status-summary:end -->
