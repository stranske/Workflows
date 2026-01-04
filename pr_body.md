<!-- pr-preamble:start -->
> **Source:** Issue #480

<!-- pr-preamble:end -->

<!-- auto-status-summary:start -->
## Automated Status Summary
#### Scope
_Scope section missing from source issue._

#### Tasks
- [x] Create task decomposition chain with `TASK_DECOMPOSITION_PROMPT`
- [x] Integrate with Formatter (#478) or Capability Check (#477)
- [x] Each sub-task must be:
- [x] - Completable in one iteration
- [x] - Have clear verification condition
- [x] - Not depend on un-merged work from other sub-tasks
- [x] Add tests for decomposition scenarios

#### Acceptance criteria
- [x] Large tasks identified and flagged for decomposition
- [x] Sub-tasks are independently verifiable
- [x] Original task context preserved
- [x] Decomposed tasks integrated into formatted issue

<!-- auto-status-summary:end -->
