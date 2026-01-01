## Keepalive Next Task

Your objective is to satisfy the **Acceptance Criteria** by completing each **Task** within the defined **Scope**.

**This round you MUST:**
1. Implement actual code or test changes that advance at least one incomplete task toward acceptance.
2. Commit meaningful source code (.py, .yml, .js, etc.)—not just status/docs updates.
3. Mark a task checkbox complete ONLY after verifying the implementation works.
4. Focus on the FIRST unchecked task unless blocked, then move to the next.

**Guidelines:**
- Keep edits scoped to the current task rather than reshaping the entire PR.
- Use repository instructions, conventions, and tests to validate work.
- Prefer small, reviewable commits; leave clear notes when follow-up is required.
- Do NOT work on unrelated improvements until all PR tasks are complete.

**COVERAGE TASKS - SPECIAL RULES:**
If a task mentions "coverage" or a percentage target (e.g., "≥95%", "to 95%"), you MUST:
1. After adding tests, run TARGETED coverage verification to avoid timeouts:
   - For a specific script like `scripts/foo.py`, run:
     `pytest tests/scripts/test_foo.py --cov=scripts/foo --cov-report=term-missing -m "not slow"`
   - If no matching test file exists, run:
     `pytest tests/ --cov=scripts/foo --cov-report=term-missing -m "not slow" -x`
2. Find the specific script in the coverage output table
3. Verify the `Cover` column shows the target percentage or higher
4. Only mark the task complete if the actual coverage meets the target
5. If coverage is below target, add more tests until it meets the target

IMPORTANT: Always use `-m "not slow"` to skip slow integration tests that may timeout.
IMPORTANT: Use targeted `--cov=scripts/specific_module` instead of `--cov=scripts` for faster feedback.

A coverage task is NOT complete just because you added tests. It is complete ONLY when the coverage command output confirms the target is met.

**The Tasks and Acceptance Criteria are provided in the appendix below.** Work through them in order.

## PR Tasks and Acceptance Criteria

**Progress:** 7/9 tasks complete, 2 remaining

### Scope
When `autofix-versions.env` is updated with new tool versions, `sync_dev_dependencies.py` correctly updates `pyproject.toml`. However, consumer repos often have a `requirements.lock` file that also pins these versions, causing CI failures due to version conflicts.

### Tasks
Complete these in order. Mark checkbox done ONLY after implementation is verified:

- [x] Extend `sync_dev_dependencies.py` with `--lockfile` flag to update `requirements.lock`
- [x] Add logic to detect and parse `requirements.lock` format (simple `package==version` lines)
- [x] Update matching package versions to align with `autofix-versions.env`
- [x] Add tests for lockfile sync functionality
- [ ] Update maint-52 sync workflow to run with `--lockfile` when `requirements.lock` exists

### Acceptance Criteria
The PR is complete when ALL of these are satisfied:

- [x] Running `sync_dev_dependencies.py --apply --lockfile` updates both `pyproject.toml` and `requirements.lock`
- [ ] CI passes without version conflicts like `ruff==0.14.10 and ruff==0.14.9`
- [x] Script gracefully handles missing `requirements.lock` (no error, just skip)
- [x] Existing `--check` mode reports lockfile mismatches
