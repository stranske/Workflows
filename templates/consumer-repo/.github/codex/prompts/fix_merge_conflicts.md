# Fix Merge Conflicts

This PR has **merge conflicts** that must be resolved before CI can run or the PR can be merged.

## Your Task

Resolve all merge conflicts by integrating changes from the base branch with this PR's changes.

## Conflict Detection

{{#if conflict_files}}
**Potentially conflicting files:**
{{#each conflict_files}}
- `{{this}}`
{{/each}}
{{else}}
Check `git status` to identify files with conflicts.
{{/if}}

## Resolution Steps

1. **Fetch latest base branch:**
   ```bash
   git fetch origin main
   ```

2. **Attempt merge:**
   ```bash
   git merge origin/main
   ```

3. **For each conflicting file:**
   - Look for conflict markers: `<<<<<<<`, `=======`, `>>>>>>>`
   - Understand what each side (HEAD vs incoming) intended
   - Combine the changes intelligently:
     - If changes are to different parts: keep both
     - If changes conflict: prefer the newer/more complete version
     - If changes are incompatible: adapt the PR's code to work with new base
   - Remove all conflict markers

4. **Verify resolution:**
   ```bash
   # Check no conflict markers remain
   git diff --check
   
   # Run tests
   pytest
   
   # Run type checks
   mypy .
   ```

5. **Commit the resolution:**
   ```bash
   git add .
   git commit -m "fix: resolve merge conflicts with main"
   ```

## Resolution Guidelines

### When to prefer PR changes:
- PR adds new functionality not in main
- PR fixes a bug that main doesn't address
- PR has more complete implementation

### When to prefer main changes:
- Main has breaking API changes PR must adapt to
- Main has bug fixes PR should incorporate
- Main renamed/moved files PR still references

### When to combine:
- Both sides add different functions/methods
- Both sides add different imports
- Both sides modify different parts of the same function

## Common Conflict Patterns

### Import conflicts:
```python
<<<<<<< HEAD
from module import foo, bar
=======
from module import foo, baz
>>>>>>> origin/main
```
**Resolution:** Combine imports: `from module import foo, bar, baz`

### Function modification conflicts:
Keep the more complete/correct version, or merge logic if both changes are needed.

### Test file conflicts:
Usually keep both sets of tests unless they're duplicates.

## Exit Criteria

- All conflict markers removed from all files
- Code compiles/parses without syntax errors
- Tests pass (at least the ones that were passing before)
- Changes committed with descriptive message

---

**Focus solely on resolving conflicts. Do not add new features or refactor code beyond what's needed for resolution.**
