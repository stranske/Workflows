# Fix CI Failures

The CI pipeline is failing. Your **only objective** is to fix the failing checks so they pass.

## Rules

**DO NOT:**
- Work on new features or tasks from the checklist
- Refactor unrelated code
- Update documentation or comments
- Make stylistic changes beyond what's needed to fix the failure

**DO:**
1. Identify which checks are failing (test, mypy, lint, type-check)
2. Read the error output carefully to understand the root cause
3. Make minimal, targeted fixes that address the specific failures
4. Verify your changes don't break other tests
5. Commit with message: `fix: resolve CI failures`

## Failure Types

### Test Failures
- Read the test name and assertion error
- Check if the test expectation is correct or if the implementation is wrong
- Fix the implementation if the test is correct
- Only modify tests if they have genuine bugs

### Mypy / Type Errors
- Read the exact error message and line number
- Add type annotations where missing
- Fix type mismatches (wrong return type, incompatible arguments)
- Use `# type: ignore` sparingly and only when truly necessary

### Lint Errors
- These are usually handled by autofix, but if you see them:
- Follow the linter's suggestion
- Don't over-engineer the fix

## Exit Criteria

Once all CI checks pass, the keepalive loop will automatically resume normal task work using the standard prompt.

---

**Focus solely on making CI green. Do not advance other work until checks pass.**
