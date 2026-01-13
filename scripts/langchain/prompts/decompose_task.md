This task is too large for a single agent iteration (~10 minutes):

{large_task}

Decompose into smaller, independently verifiable sub-tasks.

CRITICAL REQUIREMENTS - Each sub-task MUST:
1. Start with a CODING ACTION VERB: Create, Add, Update, Fix, Implement, Write, Test
2. Reference a CONCRETE DELIVERABLE: file path, function name, test case, config
3. Have a MEASURABLE verification: "tests pass", "file exists", "lint passes"
4. Be completable BY CODE - no human activities

FORBIDDEN patterns (DO NOT OUTPUT):
- "Ensure quality/clarity/completeness" (subjective, no measurable check)
- "Train staff", "Conduct sessions", "Obtain feedback" (human-only activities)
- "Review and approve" (human judgment required)
- Section headers as tasks (### Something)
- Sentence fragments (single words, punctuation only)
- Nested prefixes like "Define scope for: Define scope for: ..." (recursion)

Return sub-tasks as a markdown bullet list.
Each task should be ONE action a coding agent can complete and verify.

Example GOOD tasks:
- Create `scripts/metrics_collector.py` with `collect_timing()` function
- Add unit tests for `MetricsCollector` class in `tests/test_metrics.py`
- Update workflow to call metrics collection step after each job

Example BAD tasks (DO NOT OUTPUT):
- Ensure quality of implementation
- Train staff on new procedures
- ### Input Sanitization
- Define scope for: Define scope for: X
