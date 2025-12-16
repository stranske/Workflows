# Validation System Overview

## Goal

Provide **fast, adaptive validation** for code quality checks across the workflow repository, enabling rapid development iteration while maintaining CI alignment. The three-tier validation system allows developers to choose the right balance between speed and comprehensiveness.

## Plumbing

### Three-Tier Validation Architecture

```
┌─────────────────────┬──────────┬─────────────────────────────────┐
│ Script              │ Speed    │ Purpose                         │
├─────────────────────┼──────────┼─────────────────────────────────┤
│ dev_check.sh        │ 2-5s     │ Ultra-fast pre-commit checks    │
│ validate_fast.sh    │ 5-30s    │ Adaptive strategy validation    │
│ check_branch.sh     │ 30-120s  │ Comprehensive pre-merge checks  │
└─────────────────────┴──────────┴──────────────────────────────────┘
```

### 1. dev_check.sh - Ultra-Fast Development (2-5 seconds)

**Purpose:** Catch critical issues before commit without breaking flow

**Checks Performed:**
- ✅ Code formatting (black on scripts/ .github/)
- ✅ Critical lint errors only (E9, F codes)
- ⏳ Workflow validation (deferred to Phase 4)
- ⏳ Type checking (deferred to Phase 4)
- ⏳ Keepalive tests (deferred to Phase 5)

**Usage:**
```bash
# Quick validation (2-5s)
./scripts/dev_check.sh

# Auto-fix formatting
./scripts/dev_check.sh --fix

# Changed files only (even faster)
./scripts/dev_check.sh --changed

# Verbose output
./scripts/dev_check.sh --verbose
```

**When to Use:**
- Before every commit
- During active development
- After making small changes
- As pre-commit hook (planned Phase 2)

**Exit Codes:**
- `0`: All checks passed
- `1`: Validation failures detected

### 2. validate_fast.sh - Adaptive Strategy (5-30 seconds)

**Purpose:** Intelligent validation that adapts to change scope

**Strategy Selection:**

| Strategy | Trigger | Timing | Checks |
|----------|---------|--------|--------|
| **Incremental** | 1-3 files, no config changes | 5-10s | Critical linting + quick format |
| **Comprehensive** | Config changes or src/ changes | 10-20s | Full linting + tests for changed files |
| **Full** | >10 files or `--full` flag | 20-30s | All checks + full test suite |

**Checks Performed:**
- ✅ Code formatting (black on scripts/ .github/)
- ✅ Syntax validation per-file
- ✅ Adaptive linting based on changes
- ⏳ Import validation (deferred to Phase 4)
- ⏳ Type checking (deferred to Phase 4)
- ✅ Pytest on tests/ (for workflow tests)

**Usage:**
```bash
# Adaptive validation based on git changes
./scripts/validate_fast.sh

# Force full validation
./scripts/validate_fast.sh --full

# Auto-fix mode
./scripts/validate_fast.sh --fix

# Profile execution time
./scripts/validate_fast.sh --profile

# Changed files only (incremental)
./scripts/validate_fast.sh --changed
```

**When to Use:**
- Before opening pull request
- After rebasing or merging
- When changing multiple files
- CI pipeline fast path (planned Phase 3)

**Exit Codes:**
- `0`: All validations passed
- `1`: Validation failures detected

### 3. check_branch.sh - Comprehensive Validation (30-120 seconds)

**Purpose:** Full validation before merge, equivalent to CI checks

**Checks Performed:**
- ✅ Code formatting (black on scripts/ .github/)
- ✅ Full linting (flake8 scripts/)
- ⏳ Type checking (deferred to Phase 4)
- ⏳ Package installation (deferred to Phase 4 - N/A for workflows)
- ⏳ Import validation (deferred to Phase 4)
- ✅ Full test suite (pytest tests/)
- ⏳ Test coverage (deferred to Phase 4 - Python-specific)
- ✅ Git status check (uncommitted changes)
- ✅ Branch tracking info

**Usage:**
```bash
# Full validation (30-120s)
./scripts/check_branch.sh

# Auto-fix mode
./scripts/check_branch.sh --fix

# Skip slow tests during iteration
./scripts/check_branch.sh --fast

# Verbose output
./scripts/check_branch.sh --verbose
```

**When to Use:**
- Before requesting code review
- Before merging to main
- After Codex makes automated changes
- Final validation before deploy

**Exit Codes:**
- `0`: All validations passed, ready to merge
- `1`: Validation failures, merge blocked

### Tool Version Synchronization

All scripts enforce tool version alignment with CI using:

**PIN_FILE:** `.github/workflows/autofix-versions.env`
```bash
BLACK_VERSION=25.11.0
RUFF_VERSION=0.14.7
ISORT_VERSION=7.0.0
DOCFORMATTER_VERSION=1.7.7
MYPY_VERSION=1.19.0
PYTEST_VERSION=9.0.1
PYTEST_COV_VERSION=7.0.0
PYTEST_XDIST_VERSION=3.8.0
COVERAGE_VERSION=7.12.0
```

**Sync Script:** `scripts/sync_tool_versions.py`
```bash
# Check alignment with pyproject.toml
python -m scripts.sync_tool_versions --check

# Apply aligned versions to pyproject.toml
python -m scripts.sync_tool_versions --apply
```

This ensures local validation matches CI exactly, preventing "works on my machine" issues.

## Current Status (Phase 1)

### ✅ Completed

- All three validation scripts extracted and adapted
- Tool version synchronization infrastructure
- Virtual environment setup
- Dev dependencies installation
- Basic validation passing (dev_check.sh)

### ⏳ Deferred Work

**Phase 4 (Week 7-9): Workflow Validation System**
- Replace Python import validation with workflow YAML validation
- Add actionlint or workflow-specific validation
- Update type checking for workflow context
- Remove Python package-specific checks (coverage, pip install)
- **Estimated time:** 6 hours

**Phase 5 (Week 10-12): Keepalive System Integration**
- Extract keepalive harness infrastructure
- Update keepalive test paths
- Integrate with validation scripts
- **Estimated time:** 2 hours

**Phase 1 Completion (Week 2-3):**
- Complete this documentation
- **Estimated time:** 15 minutes remaining

**Total deferred work:** ~9 hours across 3 phases

## Quick Reference

### Comparison Matrix

| Feature | dev_check.sh | validate_fast.sh | check_branch.sh |
|---------|--------------|------------------|-----------------|
| **Speed** | 2-5s | 5-30s | 30-120s |
| **Formatting** | ✅ | ✅ | ✅ |
| **Critical Linting** | ✅ | ✅ (adaptive) | ✅ (full) |
| **Type Checking** | ⏳ Phase 4 | ⏳ Phase 4 | ⏳ Phase 4 |
| **Tests** | ❌ | ✅ (changed) | ✅ (full) |
| **Coverage** | ❌ | ❌ | ⏳ Phase 4 |
| **Workflow Validation** | ⏳ Phase 4 | ⏳ Phase 4 | ⏳ Phase 4 |
| **Auto-fix** | ✅ | ✅ | ✅ |
| **Changed Files** | ✅ | ✅ | ❌ |

### Common Workflows

**Active Development:**
```bash
# Make changes
vim scripts/some_script.py

# Quick check (2-5s)
./scripts/dev_check.sh

# Auto-fix if needed
./scripts/dev_check.sh --fix

# Commit
git add -A && git commit -m "Update script"
```

**Before Pull Request:**
```bash
# Adaptive validation (5-30s)
./scripts/validate_fast.sh

# Full validation (30-120s)
./scripts/check_branch.sh

# Open PR
gh pr create
```

**After Codex Changes:**
```bash
# Check what Codex changed
git status

# Full validation with auto-fix
./scripts/check_branch.sh --fix --verbose

# Review and commit
git add -A && git commit -m "Codex updates"
```

## Integration Points

### Phase 2: Git Hooks
- dev_check.sh as pre-commit hook
- validate_fast.sh as pre-push hook
- Bypass flags for emergencies

### Phase 3: GitHub Actions
- validate_fast.sh in fast CI path
- check_branch.sh in comprehensive CI
- Parallel execution with caching

### Phase 4: Workflow Validation
- Add actionlint integration
- YAML schema validation
- Workflow syntax checks
- Replace Python-specific validation

### Phase 5: Keepalive System
- Extract keepalive harness tests
- Integrate with dev_check.sh
- CI/CD pipeline health checks

## Troubleshooting

### "Missing .github/workflows/autofix-versions.env"
All validation scripts require the PIN_FILE. If missing:
```bash
# Should exist at:
ls -la .github/workflows/autofix-versions.env

# If missing, re-extract from Phase 1
```

### "Tool version pins are out of sync"
Run sync script to align pyproject.toml with PIN_FILE:
```bash
python -m scripts.sync_tool_versions --check  # See differences
python -m scripts.sync_tool_versions --apply  # Apply alignment
```

### "Virtual environment not activated"
Scripts will attempt auto-activation:
```bash
# Manual activation
source .venv/bin/activate

# Or let scripts handle it
./scripts/dev_check.sh  # Will activate automatically
```

### Validation warnings about deferred checks
Expected during Phase 1-3. Yellow warnings indicate functionality deferred to later phases:
- ⚠ Workflow validation → Phase 4
- ⚠ Type checking → Phase 4
- ⚠ Keepalive tests → Phase 5

These are tracked in [PHASE1_DEFERRED_ADAPTATIONS.md](../PHASE1_DEFERRED_ADAPTATIONS.md)

## File Locations

```
.
├── .github/workflows/
│   └── autofix-versions.env          # Tool version pins
├── scripts/
│   ├── dev_check.sh                  # Ultra-fast (2-5s)
│   ├── validate_fast.sh              # Adaptive (5-30s)
│   ├── check_branch.sh               # Comprehensive (30-120s)
│   └── sync_tool_versions.py         # Version synchronization
├── pyproject.toml                    # Dev dependencies + tool config
└── docs/validation/
    └── overview.md                   # This file
```

## Next Steps

1. ✅ Phase 1 validation system extraction (completed)
2. ⏳ Phase 2: Git hooks integration (Week 4-5)
3. ⏳ Phase 3: GitHub Actions CI pipeline (Week 6)
4. ⏳ Phase 4: Workflow validation system (Week 7-9)
5. ⏳ Phase 5: Keepalive system integration (Week 10-12)

---

**Last Updated:** 2025-12-16  
**Status:** Phase 1 Complete - Core validation infrastructure operational with deferred work tracked
