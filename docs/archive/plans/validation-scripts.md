# Branch Validation Scripts

## Overview
These scripts help validate Codex commits before merging them into the main development branches.

## Scripts

### `check_branch.sh` - Full Validation
**Purpose**: Comprehensive validation of Codex commits before merging  
**Usage**: `./scripts/check_branch.sh [--verbose]`

**What it checks:**
- ✅ Code formatting (Black)
- ✅ Linting (Flake8) 
- ✅ Type checking (MyPy)
- ✅ Package installation
- ✅ Import validation
- ✅ Unit tests
- ✅ Test coverage (70% minimum)
- ✅ Git status and branch info

**Options:**
- `--verbose`: Show detailed output for failed checks

**Workflow:**
1. Codex makes commits to a branch
2. Run `./scripts/check_branch.sh` to validate
3. If issues found, request Codex to fix specific problems
4. Re-run validation until all checks pass
5. Merge when validation succeeds

### `quick_check.sh` - Fast Development Check
**Purpose**: Quick validation during development  
**Usage**: `./scripts/quick_check.sh`

**What it checks:**
- ✅ Code formatting
- ✅ Recent file changes
- ✅ Basic imports

## Example Usage

```bash
# After Codex makes commits
./scripts/check_branch.sh

# For detailed error output
./scripts/check_branch.sh --verbose

# Quick check during development
./scripts/quick_check.sh
```

## Integration with Codex Workflow

1. **Before requesting Codex changes**: Run validation to establish baseline
2. **After Codex commits**: Run `check_branch.sh` to validate changes
3. **If validation fails**: Provide specific error details to Codex for fixing
4. **Before merging**: Ensure all validations pass

## Common Issues and Solutions

| Issue | Solution |
|-------|----------|
| Black formatting | Ask Codex to run `black .` |
| Flake8 errors | Ask Codex to fix specific linting issues |
| MyPy errors | Ask Codex to add type hints or fix type issues |
| Test failures | Ask Codex to fix failing tests |
| Low coverage | Ask Codex to add tests for uncovered code |

## Exit Codes

- `0`: All validations passed
- `1`: Some validations failed

## CI Integration

### Manual Workflow Triggering

The Gate workflow can be manually triggered from the GitHub interface or via the GitHub CLI without requiring new commits:

**Via GitHub UI:**
1. Navigate to **Actions** tab in the repository
2. Select the **Gate** workflow
3. Click **Run workflow** button
4. Choose the branch (defaults to main)
5. Click **Run workflow** to trigger

**Via GitHub CLI:**
```bash
# Trigger on default branch (main)
gh workflow run pr-00-gate.yml

# Trigger on specific branch
gh workflow run pr-00-gate.yml --ref branch-name
```

**Via GitHub API:**
```bash
curl -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: token YOUR_TOKEN" \
  https://api.github.com/repos/stranske/Trend_Model_Project/actions/workflows/pr-00-gate.yml/dispatches \
  -d '{"ref":"main"}'
```

This is useful for:
- Re-running CI after infrastructure changes
- Validating changes without additional commits
- Testing CI workflow modifications
- Re-triggering failed runs due to transient issues
