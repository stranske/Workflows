Your objective is to satisfy the **Acceptance Criteria** by completing each **Task** within the defined **Scope**.

**This round you MUST:**
1. Implement actual code or test changes that advance at least one incomplete task toward acceptance.
2. Commit meaningful source code (.py, .yml, .js, etc.)—not just status/docs updates.
3. **UPDATE THE CHECKBOXES** in the Tasks and Acceptance Criteria sections below to mark completed items.
4. Change `- [ ]` to `- [x]` for items you have completed and verified.
5. **In your final summary**, list completed tasks using the format: `✅ Completed: [exact task text]`

**CRITICAL - Checkbox Updates:**
When you complete a task or acceptance criterion, update its checkbox directly in this prompt file. Change the `[ ]` to `[x]` for completed items. The automation will read these checkboxes and update the PR's status summary.

**CRITICAL - Summary Format:**
At the end of your work, include explicit completion markers for each task you finished:
```
✅ Completed: Add validation for user input
✅ Completed: Write unit tests for validator module
```
This helps the automation accurately track which tasks were addressed in this round.

**Example:**
Before: `- [ ] Add validation for user input`
After:  `- [x] Add validation for user input`

**DO NOT:**
- Commit only status files, markdown summaries, or documentation when tasks require code.
- Mark checkboxes complete without actually implementing and verifying the work.
- Close the round without source-code changes when acceptance criteria require them.
- Change the text of checkboxes—only change `[ ]` to `[x]`.

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

**CONTEXT TIP:**
If the PR body includes a **Source** section with links to a parent issue or original PR, those contain additional context about the problem being solved. Check the linked issue/PR for background information, related discussions, or details not captured in the Scope section.

Review the Scope/Tasks/Acceptance below, identify the next incomplete task that requires code, implement it, then **update the checkboxes** to mark completed items.
