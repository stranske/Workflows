<!-- pr-preamble:start -->
> **Source:** Issue #480

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [ ] Create task decomposition chain with `TASK_DECOMPOSITION_PROMPT`
- [ ] Integrate with Formatter (#478) or Capability Check (#477)
- [ ] Each sub-task must be:
- [ ] - Completable in one iteration
- [ ] - Have clear verification condition
- [ ] - Not depend on un-merged work from other sub-tasks
- [ ] Add tests for decomposition scenarios

#### Acceptance criteria
- [ ] Large tasks identified and flagged for decomposition
- [ ] Sub-tasks are independently verifiable
- [ ] Original task context preserved
- [ ] Decomposed tasks integrated into formatted issue

<!-- auto-status-summary:end -->
