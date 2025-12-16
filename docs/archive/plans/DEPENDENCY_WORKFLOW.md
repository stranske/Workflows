# Dependency Enforcement Workflow

## The Complete Automation Chain

### 1️⃣ Developer adds a new import to a test

```python
# tests/test_something.py
import new_package  # <-- Not in requirements.txt yet
```

### 2️⃣ Local pre-commit hook catches it (if installed)

```bash
$ git commit -m "Add new test"
🔍 Checking test dependencies...
❌ Test dependencies are not synchronized!

Auto-fixing with: python scripts/sync_test_dependencies.py --fix
⚠️  Found 1 undeclared dependencies:
  - new_package

✅ Added 1 dependencies to requirements.txt
Please run: uv pip compile pyproject.toml -o requirements.lock

✅ Fixed! Please review and stage the changes to requirements.txt

Run: git add pyproject.toml
```

### 3️⃣ Developer reviews and commits the fix

```bash
$ git add pyproject.toml requirements.lock
$ git commit -m "Add new_package dependency"
✅ All test dependencies are declared
[codex/feature 1234567] Add new_package dependency
 2 files changed, 2 insertions(+)
```

### 4️⃣ CI validates on pull request

If the developer didn't have the pre-commit hook:

```yaml
# CI detects missing dependency
❌ Check for undeclared test dependencies
⚠️  Found 1 undeclared dependencies:
  - new_package

# CI auto-fixes and shows the fix
✅ Auto-fix missing dependencies
⚠️ Found undeclared test dependencies. Auto-fixing...
⚠️  Found 1 undeclared dependencies:
  - new_package

✅ Added 1 dependencies to requirements.txt
📝 Updated requirements.txt with missing dependencies.
⚠️ Build will fail - commit the updated requirements.txt

# Build fails to force manual commit
❌ Build failed
```

### 5️⃣ Developer updates PR with the auto-generated fix

Pull the CI's generated changes (shown in job summary), commit, and push:

```bash
$ # Copy the missing line from CI output to requirements.txt
$ echo "new_package" >> requirements.txt
$ uv pip compile pyproject.toml -o requirements.lock
$ git add pyproject.toml requirements.lock
$ git commit -m "Add missing new_package dependency"
$ git push
```

### 6️⃣ CI passes ✅

```
✅ Check for undeclared test dependencies
✅ All test dependencies are declared in requirements.txt

✅ Run tests
2102 passed, 0 skipped
```

---

## Manual Workflow (Without Pre-commit Hook)

### Check for missing dependencies

```bash
python scripts/sync_test_dependencies.py
```

### Fix automatically

```bash
python scripts/sync_test_dependencies.py --fix
uv pip compile pyproject.toml -o requirements.lock
git add pyproject.toml requirements.lock
```

### Verify in CI mode

```bash
python scripts/sync_test_dependencies.py --verify
# Exit code 0 = all good
# Exit code 1 = missing dependencies found
```

---

## Install Pre-commit Hook

```bash
cp scripts/pre-commit-check-deps.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

Now every commit automatically checks and fixes dependencies before allowing the commit.

---

## Key Benefits

1. **Can't forget dependencies** - Tests fail if you import without declaring
2. **Auto-fix available** - One command syncs everything
3. **CI enforces** - Can't merge without declaring dependencies
4. **Pre-commit optional** - Catches issues before CI
5. **Clear errors** - Tells you exactly what to run to fix
6. **Git history clean** - All dependency changes are explicit commits

---

## Troubleshooting

### "Script not found" error

Make sure you're in the repository root:
```bash
cd /workspaces/Trend_Model_Project
python scripts/sync_test_dependencies.py
```

### False positives (stdlib modules detected)

Update `STDLIB_MODULES` in `scripts/sync_test_dependencies.py` and `tests/test_dependency_enforcement.py` to match.

### Package name != module name (like PyYAML → yaml)

Add to `MODULE_TO_PACKAGE` mapping in both files:
```python
MODULE_TO_PACKAGE = {
    "yaml": "PyYAML",
    ...
}
```
