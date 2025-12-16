# Git Hooks Overview

## Goal

Automate code quality validation at git commit and push events, ensuring consistent code quality before changes reach remote repository. The two-tier hook system provides fast feedback during development while maintaining comprehensive validation before sharing code.

## Plumbing

### Hook Architecture

```
┌─────────────────────┬──────────┬─────────────────────────────────┐
│ Hook Type           │ Speed    │ Triggered By                    │
├─────────────────────┼──────────┼─────────────────────────────────┤
│ pre-commit          │ 2-5s     │ git commit                      │
│ pre-push            │ 5-30s    │ git push                        │
└─────────────────────┴──────────┴──────────────────────────────────┘
```

### Pre-Commit Framework

We use [pre-commit](https://pre-commit.com/) framework for managing git hooks. This provides:
- Automatic hook installation and updates
- Language-agnostic hook management
- Easy hook sharing across team
- Consistent behavior across environments

### Hook Configuration: .pre-commit-config.yaml

The `.pre-commit-config.yaml` file defines all hooks. It's organized into sections:

1. **Standard Hooks** - File cleanup (trailing whitespace, end-of-file)
2. **YAML Validation** - Check YAML syntax (excluding GitHub Actions special syntax)
3. **Code Formatting** - Black formatter, Ruff linter
4. **Custom Validation** - dev_check.sh and validate_fast.sh

### Installation

**One-time setup:**
```bash
# Install pre-commit (already in dev dependencies)
pip install pre-commit

# Install git hooks
pre-commit install --hook-type pre-commit --hook-type pre-push

# Verify installation
pre-commit --version
```

**Result:**
- `.git/hooks/pre-commit` - Runs dev_check.sh (2-5s)
- `.git/hooks/pre-push` - Runs validate_fast.sh (5-30s)

### Hook Details

#### 1. Pre-Commit Hook (git commit)

**Triggers:** Every `git commit` command

**What Runs:**
1. **Trailing whitespace cleanup** (auto-fix)
2. **End-of-file fixer** (auto-fix)
3. **YAML validation** (check syntax)
4. **Large file detection** (reject >1MB files)
5. **Shebang validation** (verify shell scripts executable)
6. **Black formatting** (Python code)
7. **Ruff linting** (Python code, auto-fix)
8. **dev_check.sh** - Ultra-fast validation (2-5s)
   - Code formatting check
   - Critical lint errors only
   - ⏳ Workflow validation (Phase 4)
   - ⏳ Type checking (Phase 4)

**Expected Timing:** 2-5 seconds total

**Bypass for emergencies:**
```bash
git commit --no-verify -m "Emergency fix"
```

#### 2. Pre-Push Hook (git push)

**Triggers:** Every `git push` command

**What Runs:**
- **validate_fast.sh** - Adaptive validation (5-30s)
  - Analyzes changed files
  - Selects strategy: incremental (1-3 files) / comprehensive (config changes) / full (>10 files)
  - Code formatting
  - Adaptive linting
  - Tests for changed files

**Expected Timing:** 5-30 seconds depending on changes

**Bypass for emergencies:**
```bash
git push --no-verify
```

### Usage Examples

#### Normal Development Workflow

```bash
# Make changes
vim scripts/some_script.py

# Add to staging
git add scripts/some_script.py

# Commit (triggers pre-commit hook)
git commit -m "Update script"
# → Runs in 2-5s, auto-fixes formatting, validates syntax

# Push (triggers pre-push hook)
git push
# → Runs in 5-30s, validates changed files adaptively
```

#### Manual Hook Execution

```bash
# Run all hooks on all files
pre-commit run --all-files

# Run specific hook
pre-commit run dev-check
pre-commit run validate-fast
pre-commit run black

# Run hooks on specific files
pre-commit run --files scripts/*.py
```

#### Skip Hooks (Emergency Only)

```bash
# Skip pre-commit hook
git commit --no-verify -m "Emergency: bypass validation"

# Skip pre-push hook
git push --no-verify

# WARNING: Use sparingly! Bypassed commits may break CI
```

#### Update Hook Versions

```bash
# Update all hooks to latest versions
pre-commit autoupdate

# This updates .pre-commit-config.yaml with latest revisions
```

### Hook Configuration Details

#### Excluded Files

Hooks skip these patterns (defined in `.pre-commit-config.yaml`):
- `^archive/` - Archived code
- `^\.extraction/` - Temporary extraction files
- `^\.venv/` - Virtual environment
- `^build/`, `^dist/` - Build artifacts

#### File Type Filters

Different hooks apply to different file types:
- **Python files:** `\.(py|pyi)$` - Black, Ruff, dev_check.sh
- **Shell scripts:** `\.sh$` - Shebang checks, dev_check.sh
- **YAML files:** `\.ya?ml$` - YAML validation (except `.github/workflows/`)

#### Hook Dependencies

- **Python 3.11+** - Required for Black, Ruff
- **Bash** - Required for dev_check.sh, validate_fast.sh
- **Git** - Obviously required for hooks

### Integration with Validation Scripts

The git hooks leverage the validation scripts extracted in Phase 1:

```
Pre-Commit Hook
    ↓
[Standard hooks: whitespace, YAML, etc.]
    ↓
dev_check.sh (2-5s)
    ├── Code formatting check
    ├── Critical linting
    └── ⏳ Workflow validation (Phase 4)

Pre-Push Hook
    ↓
validate_fast.sh (5-30s)
    ├── Change analysis
    ├── Strategy selection
    ├── Adaptive validation
    └── Tests on changed files
```

### Current Status (Phase 2)

#### ✅ Completed

- Pre-commit framework installed and configured
- `.pre-commit-config.yaml` created with immediate adaptations
- Pre-commit hook installed (runs dev_check.sh)
- Pre-push hook installed (runs validate_fast.sh)
- Hook bypass instructions documented
- Tested: pre-commit runs in 1.74s ✅

#### ⏳ Deferred Work

**Phase 4 (Week 7-9): Workflow Validation**
- Add actionlint hook for `.github/workflows/*.yaml` validation
- Uncomment actionlint section in `.pre-commit-config.yaml`
- **Estimated time:** 1 hour

**Phase 6 (Week 13-15): Notebook Support (Optional)**
- Extract `tools/strip_output.py` if notebooks needed
- Add strip-notebook-outputs hook
- **Estimated time:** 2 hours (only if notebooks added)

See [PHASE2_DEFERRED_ADAPTATIONS.md](../PHASE2_DEFERRED_ADAPTATIONS.md) for details.

### Troubleshooting

#### "pre-commit: command not found"

Install pre-commit in virtual environment:
```bash
source .venv/bin/activate
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push
```

#### Hooks not running

Verify installation:
```bash
# Check installed hooks
ls -la .git/hooks/

# Should see:
# pre-commit (points to pre-commit framework)
# pre-push (points to pre-commit framework)

# Reinstall if missing
pre-commit install --install-hooks --hook-type pre-commit --hook-type pre-push
```

#### Hook fails with "Permission denied"

Ensure validation scripts are executable:
```bash
chmod +x scripts/*.sh
git add scripts/*.sh
git commit -m "Make scripts executable"
```

#### Hook takes too long

**For pre-commit (>5s):**
- Should be fast (2-5s). If slower, check for:
  - Large number of changed files (use `--changed` flag in dev_check.sh)
  - Network issues (tool version sync)

**For pre-push (>30s):**
- Expected for large changesets
- Consider using `--fast` mode during active development
- Or bypass with `--no-verify` and run manually later

#### Want to skip specific hook

Edit `.pre-commit-config.yaml` and set `stages: [manual]` for hook:
```yaml
- id: validate-fast
  stages: [manual]  # Won't run automatically
```

Then run manually when needed:
```bash
pre-commit run validate-fast --all-files
```

### Comparison with CI

| Check | Pre-Commit Hook | Pre-Push Hook | GitHub Actions CI |
|-------|-----------------|---------------|-------------------|
| **Speed** | 2-5s | 5-30s | 2-10min |
| **When** | Every commit | Every push | Every PR/push |
| **Formatting** | ✅ Auto-fix | ✅ Check | ✅ Check |
| **Linting** | ✅ Critical only | ✅ Adaptive | ✅ Full |
| **Type Check** | ⏳ Phase 4 | ⏳ Phase 4 | ⏳ Phase 4 |
| **Tests** | ❌ | ✅ Changed files | ✅ Full suite |
| **Coverage** | ❌ | ❌ | ⏳ Phase 4 |
| **Bypassable** | ✅ --no-verify | ✅ --no-verify | ❌ Must pass |

**Philosophy:**
- **Pre-commit:** Catch obvious issues immediately (formatting, critical linting)
- **Pre-push:** Validate changed files before sharing (adaptive testing)
- **CI:** Comprehensive validation, merge gatekeeper (full test suite)

### Advanced Configuration

#### Custom Hook Arguments

Modify hook behavior in `.pre-commit-config.yaml`:

```yaml
- id: dev-check
  entry: ./scripts/dev_check.sh --fix  # Auto-fix mode
  
- id: validate-fast
  entry: ./scripts/validate_fast.sh --verbose  # Show details
```

#### Conditional Hook Execution

Run hooks only on specific file patterns:
```yaml
- id: dev-check
  files: '\.(py|sh)$'  # Only Python and shell files
```

#### Hook Environments

Pre-commit isolates each hook in its own environment:
- Black hook: Isolated Python environment with Black installed
- Ruff hook: Isolated environment with Ruff
- Local hooks (dev_check.sh): Use system environment

### File Locations

```
.
├── .pre-commit-config.yaml          # Hook configuration
├── .git/hooks/
│   ├── pre-commit                   # Installed by pre-commit framework
│   └── pre-push                     # Installed by pre-commit framework
├── scripts/
│   ├── dev_check.sh                 # Called by pre-commit hook
│   └── validate_fast.sh             # Called by pre-push hook
└── docs/git-hooks/
    └── overview.md                  # This file
```

### Next Steps

1. ✅ Phase 2 git hooks (completed)
2. ⏳ Phase 3: GitHub Actions CI pipeline (Week 6)
   - Extract `.github/workflows/` from Trend_Model_Project
   - Adapt for workflow repository
   - Integrate validation scripts
3. ⏳ Phase 4: Workflow validation system (Week 7-9)
   - Add actionlint hook
   - Replace Python-specific validation with workflow validation
4. ⏳ Phase 5: Keepalive system integration (Week 10-12)

---

**Last Updated:** 2025-12-16  
**Status:** Phase 2 Complete - Git hooks operational with pre-commit framework
