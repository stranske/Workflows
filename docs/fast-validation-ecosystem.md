# Fast Validation Ecosystem for Codex Development

This document describes the optimized validation workflow designed for efficient Codex-assisted development, where speed and automation are crucial for maintaining code quality without interrupting the development flow.

## Overview

The validation ecosystem consists of multiple tools designed for different scenarios:

- **Ultra-fast checks** for immediate feedback during development
- **Intelligent validation** that adapts based on what changed
- **Comprehensive validation** for pre-merge confidence
- **Automated Git hooks** for seamless integration

## Validation Tools

### 1. `dev_check.sh` - Ultra-Fast Development Validation

**Purpose**: Immediate feedback during active development  
**Speed**: 2-5 seconds  
**Usage**: After every few Codex changes

```bash
# Check everything quickly
./scripts/dev_check.sh

# Auto-fix formatting issues
./scripts/dev_check.sh --fix

# Only check files you've modified
./scripts/dev_check.sh --changed

# See detailed output
./scripts/dev_check.sh --verbose
```

**What it checks**:
- Syntax errors (instant failure)
- Import validation
- Code formatting (Black)
- Critical lint errors only (E9**, F***)
- Basic type checking

### 2. `validate_fast.sh` - Intelligent Adaptive Validation

**Purpose**: Smart validation that adapts to your changes  
**Speed**: 5-30 seconds depending on changes  
**Usage**: Before commits or when Codex makes substantial changes

```bash
# Automatic strategy selection
./scripts/validate_fast.sh

# Force comprehensive validation
./scripts/validate_fast.sh --full

# Auto-fix what can be fixed
./scripts/validate_fast.sh --fix

# Check specific commit range
./scripts/validate_fast.sh --commit-range=HEAD~3

# Profile performance
./scripts/validate_fast.sh --profile
```

**Validation Strategies**:

1. **Incremental** (1-3 Python files changed):
   - Critical linting only
   - Basic type checking on changed files
   - Skip expensive tests

2. **Comprehensive** (config changes, >3 files, src/ changes):
   - Full linting
   - Complete type checking
   - Run tests if test files changed

3. **Full** (>10 files or --full flag):
   - All validations
   - Complete test suite
   - Coverage requirements

### 3. `quick_check.sh` - Legacy Quick Validation

**Purpose**: Simple, fast checks  
**Speed**: 3-8 seconds  
**Usage**: Basic development workflow

```bash
./scripts/quick_check.sh
```

### 4. `check_branch.sh` - Comprehensive Validation

**Purpose**: Pre-merge validation and CI-style checks  
**Speed**: 30-120 seconds  
**Usage**: Before merging, final validation

```bash
# Full validation
./scripts/check_branch.sh

# Auto-fix issues
./scripts/check_branch.sh --fix

# Skip slow tests
./scripts/check_branch.sh --fast

# Detailed output
./scripts/check_branch.sh --verbose
```

### 5. `fix_common_issues.sh` - Auto-Fix Common Problems

**Purpose**: Automatically fix common Codex issues  
**Speed**: 5-15 seconds  
**Usage**: When validation fails with fixable issues

```bash
./scripts/fix_common_issues.sh
```

**What it fixes**:
- Code formatting with Black
- Missing type stubs
- Common import issues
- Basic line length problems

## Git Hooks Integration

### Setup

```bash
# Install all hooks
./scripts/git_hooks.sh install

# Check status
./scripts/git_hooks.sh status

# Remove hooks
./scripts/git_hooks.sh uninstall
```

### Installed Hooks

1. **pre-commit**: Fast validation before each commit
2. **pre-push**: Comprehensive validation before pushing
3. **post-commit**: Status notification after commits

### Bypassing Hooks

```bash
# Skip pre-commit validation
git commit --no-verify

# Skip pre-push validation
git push --no-verify
```

## Recommended Workflows

### 1. Active Development Workflow

```bash
# After Codex makes changes
./scripts/dev_check.sh --changed --fix

# If issues found, fix them
./scripts/fix_common_issues.sh

# Continue development...
```

### 2. Pre-Commit Workflow

```bash
# Before committing
./scripts/validate_fast.sh --fix

# If comprehensive validation needed
./scripts/validate_fast.sh --full

# Commit with automatic validation (if hooks installed)
git commit -m "Your message"
```

### 3. Pre-Push Workflow

```bash
# Before pushing to shared branch
./scripts/check_branch.sh --fast

# Or let the pre-push hook handle it
git push origin your-branch
```

### 4. Codex Integration Workflow

For large Codex-generated changes:

```bash
# 1. Quick syntax/import check
./scripts/dev_check.sh --changed

# 2. If OK, intelligent validation
./scripts/validate_fast.sh

# 3. Auto-fix common issues
./scripts/validate_fast.sh --fix

# 4. Final check before commit
./scripts/check_branch.sh --fast
```

## Performance Optimization

### Speed Comparison

| Tool | Typical Speed | Use Case |
|------|--------------|----------|
| `dev_check.sh` | 2-5s | During development |
| `validate_fast.sh` (incremental) | 5-15s | Small changes |
| `validate_fast.sh` (comprehensive) | 15-30s | Significant changes |
| `validate_fast.sh --full` | 30-60s | Major changes |
| `check_branch.sh --fast` | 30-90s | Pre-merge |
| `check_branch.sh` | 60-120s | Full validation |

### Optimization Tips

1. **Use `--changed` flag** when only checking recent modifications
2. **Enable `--fix` mode** to automatically resolve formatting issues
3. **Use `--fast` mode** during development to skip expensive tests
4. **Profile with `--profile`** to identify bottlenecks
5. **Install Git hooks** for automatic validation without thinking

### File-Level Optimizations

The tools are optimized to:
- Skip unchanged files when possible
- Use parallel processing for independent checks
- Cache expensive operations
- Fail fast on syntax errors
- Only run full test suites when necessary

## Error Handling

### Common Issues and Solutions

1. **Formatting Issues**:
   ```bash
   ./scripts/validate_fast.sh --fix
   ```

2. **Import Errors**:
   ```bash
   ./scripts/fix_common_issues.sh
   ```

3. **Type Checking Issues**:
   ```bash
   mypy --install-types --non-interactive
   ./scripts/validate_fast.sh
   ```

4. **Lint Issues**:
   ```bash
   # See specific issues
   ./scripts/check_branch.sh --verbose
   ```

5. **Test Failures**:
   ```bash
   # Run specific failing tests
   pytest tests/test_specific.py -v
   ```

### Debugging Validation

```bash
# See what files changed
git diff --name-only HEAD~1

# Verbose output for all checks
./scripts/validate_fast.sh --verbose --profile

# Check specific files
black --check src/specific_file.py
flake8 src/specific_file.py
mypy src/specific_file.py
```

## Customization

### Environment Variables

```bash
# Skip certain checks
export SKIP_COVERAGE=1
export SKIP_MYPY=1

# Adjust thresholds
export COVERAGE_THRESHOLD=65
export MAX_LINE_LENGTH=88
```

### Configuration Files

- `.flake8` - Linting configuration
- `pyproject.toml` - Tool configuration (Black, MyPy, pytest, coverage)
- `config/` - Application-specific configs

## Integration with IDEs

### VS Code

1. Install Python extension
2. Configure automatic formatting on save
3. Enable type checking in settings
4. Use tasks.json for quick validation

### Command Palette Integration

Add to VS Code tasks.json:

```json
{
    "tasks": [
        {
            "label": "Quick Validation",
            "type": "shell",
            "command": "./scripts/dev_check.sh --fix",
            "group": "build",
            "presentation": {
                "echo": true,
                "reveal": "always",
                "focus": false,
                "panel": "shared"
            }
        }
    ]
}
```

## Best Practices

1. **Run validation early and often** - catch issues immediately
2. **Use auto-fix modes** to reduce manual work
3. **Install Git hooks** for automatic validation
4. **Start with fast checks** and progress to comprehensive validation
5. **Profile your workflow** to identify bottlenecks
6. **Customize thresholds** based on your project needs
7. **Keep validation tools updated** as your codebase evolves

## Troubleshooting

### Performance Issues

```bash
# Profile validation performance
./scripts/validate_fast.sh --profile

# Check if virtual environment is active
echo $VIRTUAL_ENV

# Clear cache if needed
rm -rf .mypy_cache .pytest_cache __pycache__
```

### Hook Issues

```bash
# Check hook status
./scripts/git_hooks.sh status

# Reinstall hooks
./scripts/git_hooks.sh uninstall
./scripts/git_hooks.sh install

# Test hooks manually
./.git/hooks/pre-commit
```

This ecosystem provides a comprehensive, fast, and intelligent validation workflow that scales from quick development checks to comprehensive pre-merge validation, all optimized for Codex-assisted development workflows.
