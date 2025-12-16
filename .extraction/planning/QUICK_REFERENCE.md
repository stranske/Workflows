# Quick Reference Guide - Workflow Extraction

Quick reference for extracting files from Trend_Model_Project.

## Fast Commands

### Search for Project-Specific Terms

```bash
# In the extracted file, search for these terms:
rg -i "trend.?model" FILE
rg -i "stranske" FILE  
rg -i "phase-2-dev" FILE
rg "Issue #[0-9]+" FILE
rg "3\.11|3\.12" FILE  # hardcoded Python versions
```

### Validate Extraction

```bash
# Run all checks at once:
./scripts/validate-extraction.sh FILE

# Or manually:
! grep -i "stranske" FILE
! grep -i "trend.?model" FILE  
! grep "phase-2-dev" FILE
```

## Common Find/Replace Patterns

### Repository References

| Find | Replace |
|------|---------|
| `stranske/Trend_Model_Project` | `${{ github.repository }}` |
| `Trend_Model_Project` | `${{ github.event.repository.name }}` |
| `github.com/stranske/Trend_Model_Project` | `${{ github.server_url }}/${{ github.repository }}` |

### Branch References

| Find | Replace |
|------|---------|
| `branches: [main]` | `branches: [${{ inputs.default-branch }}]` |
| `branches: [phase-2-dev]` | `branches: [${{ inputs.develop-branch }}]` |
| `refs/heads/main` | `refs/heads/${{ inputs.default-branch }}` |

### Python Specifics

| Find | Replace |
|------|---------|
| `python-version: "3.11"` | `python-version: ${{ inputs.python-version }}` |
| `pip install trend_model` | `pip install ${{ inputs.package-name }}` |
| `import trend_model` | `import ${{ env.PACKAGE_NAME }}` |
| `--cov=trend_model` | `--cov=${{ inputs.package-name }}` |

### Paths

| Find | Replace |
|------|---------|
| `tests/` (hardcoded) | `${{ inputs.test-dir || 'tests/' }}` |
| `trend_model/` | `${{ inputs.source-dir || 'src/' }}` |

## Extraction Workflow

### Step-by-Step Process

```bash
# 1. Copy file from Trend_Model_Project
cp ~/Trend_Model_Project/.github/workflows/FILE.yml .github/workflows/

# 2. Run automated scrubbing (if available)
./scripts/scrub-file.sh .github/workflows/FILE.yml

# 3. Manual review - check for patterns
rg -i "trend|stranske" .github/workflows/FILE.yml

# 4. Add parameterization
# Edit file to add inputs section

# 5. Test syntax
actionlint .github/workflows/FILE.yml

# 6. Create test
cp ~/Trend_Model_Project/tests/workflows/test_FILE.py tests/workflows/

# 7. Scrub and adapt test
./scripts/scrub-file.sh tests/workflows/test_FILE.py

# 8. Run test
pytest tests/workflows/test_FILE.py -v

# 9. Update documentation
# Add entry to README, create docs/workflows/FILE.md

# 10. Commit
git add .github/workflows/FILE.yml tests/workflows/test_FILE.py docs/
git commit -m "Extract FILE.yml workflow"
```

## Input Pattern Template

When parameterizing a workflow, use this template:

```yaml
name: Workflow Name

on:
  workflow_call:
    inputs:
      # Required inputs (no defaults)
      package-name:
        description: 'Name of the package for testing'
        required: true
        type: string
      
      # Optional inputs (with defaults)
      python-version:
        description: 'Python version to use'
        required: false
        type: string
        default: '3.11'
      
      test-dir:
        description: 'Directory containing tests'
        required: false
        type: string
        default: 'tests/'
      
      # Boolean inputs
      enable-coverage:
        description: 'Enable coverage reporting'
        required: false
        type: boolean
        default: true
    
    secrets:
      # Required secrets
      WORKFLOW_PAT:
        description: 'Personal access token for workflow operations'
        required: false  # Usually optional with fallback to GITHUB_TOKEN

    outputs:
      # Workflow outputs
      coverage-percent:
        description: 'Coverage percentage'
        value: ${{ jobs.test.outputs.coverage }}

jobs:
  test:
    runs-on: ubuntu-latest
    outputs:
      coverage: ${{ steps.coverage.outputs.percent }}
    steps:
      # Use inputs with fallbacks
      - name: Example step
        run: |
          echo "Package: ${{ inputs.package-name }}"
          echo "Python: ${{ inputs.python-version || '3.11' }}"
```

## Common Parameterization Patterns

### Python Project

```yaml
inputs:
  package-name:
    description: 'Package name'
    required: true
    type: string
  python-versions:
    description: 'JSON array of Python versions'
    required: false
    type: string
    default: '["3.11"]'
  coverage-min:
    description: 'Minimum coverage percentage'
    required: false
    type: string
    default: '0'
  test-command:
    description: 'Command to run tests'
    required: false
    type: string
    default: 'pytest tests/'
```

### Docker Project

```yaml
inputs:
  dockerfile:
    description: 'Path to Dockerfile'
    required: false
    type: string
    default: 'Dockerfile'
  image-name:
    description: 'Docker image name'
    required: true
    type: string
  smoke-test-command:
    description: 'Command to run for smoke test'
    required: false
    type: string
    default: 'echo "OK"'
```

### Generic Health Check

```yaml
inputs:
  check-type:
    description: 'Type of health check to run'
    required: true
    type: string
  config-file:
    description: 'Path to configuration file'
    required: false
    type: string
    default: '.github/health-config.yml'
```

## Documentation Template

For each extracted workflow, create `docs/workflows/WORKFLOW_NAME.md`:

```markdown
# Workflow Name

Brief description of what this workflow does.

## Usage

\`\`\`yaml
name: My CI
on: [push, pull_request]
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/WORKFLOW_NAME.yml@v1
    with:
      input1: value1
      input2: value2
\`\`\`

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `input1` | Yes | - | Description of input1 |
| `input2` | No | `default` | Description of input2 |

## Outputs

| Output | Description |
|--------|-------------|
| `output1` | Description of output1 |

## Secrets

| Secret | Required | Description |
|--------|----------|-------------|
| `SECRET_NAME` | No | Description of secret |

## Examples

### Basic Example

\`\`\`yaml
# Paste basic example here
\`\`\`

### Advanced Example

\`\`\`yaml
# Paste advanced example here
\`\`\`

## Troubleshooting

### Common Issue 1

Description of issue and solution.

### Common Issue 2

Description of issue and solution.
```

## Test Template

For each extracted workflow, create/adapt `tests/workflows/test_WORKFLOW_NAME.py`:

```python
"""Tests for WORKFLOW_NAME workflow."""
import pathlib
import yaml


WORKFLOW_FILE = pathlib.Path(".github/workflows/WORKFLOW_NAME.yml")


def test_workflow_exists():
    """Verify workflow file exists."""
    assert WORKFLOW_FILE.exists()


def test_workflow_syntax():
    """Verify workflow has valid YAML syntax."""
    with open(WORKFLOW_FILE) as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "name" in data
    assert "on" in data or "true" in data  # workflow_call or trigger


def test_workflow_has_required_inputs():
    """Verify required inputs are defined."""
    with open(WORKFLOW_FILE) as f:
        data = yaml.safe_load(f)
    
    # For workflow_call workflows
    if "workflow_call" in data.get("on", {}):
        inputs = data["on"]["workflow_call"].get("inputs", {})
        assert "required-input-name" in inputs


def test_workflow_no_hardcoded_values():
    """Verify no project-specific hardcoded values."""
    with open(WORKFLOW_FILE) as f:
        content = f.read()
    
    # Check for common hardcoded values
    assert "stranske" not in content.lower()
    assert "trend_model" not in content.lower()
    assert "phase-2-dev" not in content


def test_workflow_uses_parameterized_inputs():
    """Verify workflow uses inputs instead of hardcoded values."""
    with open(WORKFLOW_FILE) as f:
        content = f.read()
    
    # Should use inputs
    assert "${{ inputs." in content
```

## Checklist Per File

Print this for each file extraction:

```
File: _______________________

[ ] File copied from Trend_Model_Project
[ ] Automated scrubbing run
[ ] Manual review for project-specific terms
[ ] Inputs section added/updated
[ ] All hardcoded values parameterized  
[ ] Default values provided for optional inputs
[ ] Documentation comments added
[ ] Workflow syntax validated (actionlint)
[ ] Test file created/adapted
[ ] Test passes
[ ] Documentation created (docs/workflows/*.md)
[ ] Example added (if applicable)
[ ] README updated
[ ] Committed with descriptive message
```

## Priority Files Checklist

Core files to extract first (Week 1-2):

```
[ ] scripts/ci_metrics.py
[ ] scripts/ci_history.py
[ ] scripts/ci_coverage_delta.py
[ ] scripts/workflow_lint.sh
[ ] .github/actions/autofix/
[ ] .github/workflows/reusable-10-ci-python.yml
[ ] tests/workflows/test_reusable_ci_workflow.py
[ ] docs/ci-workflow.md (adapted)
```

## Quick Validation Script

Save as `scripts/validate-extraction.sh`:

```bash
#!/bin/bash
# Quick validation of extracted file

FILE=$1

if [ -z "$FILE" ]; then
    echo "Usage: $0 <file>"
    exit 1
fi

echo "Validating $FILE..."

ERRORS=0

# Check for project-specific terms
if grep -qi "stranske" "$FILE"; then
    echo "❌ Contains 'stranske'"
    ERRORS=$((ERRORS + 1))
fi

if grep -qi "trend.?model" "$FILE"; then
    echo "❌ Contains 'trend_model' or similar"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "phase-2-dev" "$FILE"; then
    echo "❌ Contains 'phase-2-dev'"
    ERRORS=$((ERRORS + 1))
fi

if grep -q "Issue #[0-9]" "$FILE"; then
    echo "⚠️  Contains issue references (may be OK in docs)"
fi

# For workflow files, check for parameterization
if [[ "$FILE" == *.yml ]] || [[ "$FILE" == *.yaml ]]; then
    if ! grep -q '\${{ inputs\.' "$FILE"; then
        echo "⚠️  Workflow doesn't use inputs (may need parameterization)"
    fi
    
    # Validate YAML syntax
    if command -v yq &> /dev/null; then
        if ! yq eval '.' "$FILE" > /dev/null 2>&1; then
            echo "❌ Invalid YAML syntax"
            ERRORS=$((ERRORS + 1))
        fi
    fi
fi

if [ $ERRORS -eq 0 ]; then
    echo "✅ Validation passed"
    exit 0
else
    echo "❌ Validation failed with $ERRORS errors"
    exit 1
fi
```

Make it executable:
```bash
chmod +x scripts/validate-extraction.sh
```

## Quick Links

- **Main Plan**: [TRANSITION_PLAN.md](TRANSITION_PLAN.md)
- **Scrubbing Guide**: [SCRUBBING_CHECKLIST.md](SCRUBBING_CHECKLIST.md)
- **Priority Matrix**: [EXTRACTION_PRIORITY.md](EXTRACTION_PRIORITY.md)
- **Source Repo**: https://github.com/stranske/Trend_Model_Project

---

**Document Version**: 1.0  
**Last Updated**: 2024-12-16  
**Status**: Ready for Use

**Usage**: Keep this open while extracting files for quick reference.
