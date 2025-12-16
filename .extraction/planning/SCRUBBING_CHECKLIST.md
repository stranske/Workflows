# Scrubbing Checklist - Removing Trend_Model_Project Specifics

This document provides a detailed checklist of project-specific elements that must be removed or generalized when extracting workflows from Trend_Model_Project.

## General Patterns to Find and Replace

### Repository References

**Find:**
```
stranske/Trend_Model_Project
Trend_Model_Project
trend_model_project
github.com/stranske/Trend_Model_Project
```

**Replace with:**
```
${{ github.repository }}
${{ inputs.repository }}
[Template variable or configurable input]
```

### Branch References

**Find:**
```
branches: [main]
branches: [phase-2-dev]
if: github.ref == 'refs/heads/main'
if: github.ref == 'refs/heads/phase-2-dev'
```

**Replace with:**
```
branches: [${{ inputs.default-branch }}]
branches: [${{ inputs.develop-branch }}]
if: github.ref == format('refs/heads/{0}', inputs.default-branch)
[Configurable input with default 'main']
```

### Hardcoded URLs

**Find:**
```
https://github.com/stranske/Trend_Model_Project/actions/workflows/
https://github.com/stranske/Trend_Model_Project/actions/runs/
[any stranske/Trend_Model_Project URL]
```

**Replace with:**
```
${{ github.server_url }}/${{ github.repository }}/actions/workflows/
${{ github.server_url }}/${{ github.repository }}/actions/runs/
[Dynamic URL construction]
```

## File-by-File Scrubbing Guide

### reusable-10-ci-python.yml

#### Remove/Generalize:

1. **Python Version Pins:**
   ```yaml
   # OLD (hardcoded)
   python-version: "3.11"
   matrix: { python-version: ["3.11", "3.12"] }
   
   # NEW (parameterized)
   python-version: ${{ inputs.python-version }}
   matrix: { python-version: ${{ fromJSON(inputs.python-versions) }} }
   ```

2. **Coverage Baselines:**
   ```yaml
   # OLD (project-specific)
   baseline-coverage: '75.5'
   coverage-min: '72'
   
   # NEW (parameterized)
   baseline-coverage: ${{ inputs.baseline-coverage || '0' }}
   coverage-min: ${{ inputs.coverage-min }}
   ```

3. **Package Installation:**
   ```yaml
   # OLD (project-specific)
   pip install -e .
   pip install trend_model[test]
   
   # NEW (configurable)
   pip install ${{ inputs.install-command }}
   # Or
   ${{ inputs.install-script }}
   ```

4. **Test Commands:**
   ```yaml
   # OLD (assumed structure)
   pytest tests/ --cov=trend_model
   
   # NEW (configurable)
   ${{ inputs.test-command }}
   # With default: pytest tests/ --cov=${{ inputs.package-name }}
   ```

5. **Artifact Names:**
   ```yaml
   # OLD (project-specific)
   name: gate-coverage
   name: gate-coverage-summary
   
   # NEW (parameterized)
   name: ${{ inputs.artifact-prefix }}-coverage
   name: ${{ inputs.artifact-prefix }}-coverage-summary
   ```

6. **Mypy Configuration:**
   ```yaml
   # OLD (hardcoded)
   mypy trend_model tests
   
   # NEW (configurable)
   mypy ${{ inputs.mypy-targets }}
   ```

7. **Ruff/Black Paths:**
   ```yaml
   # OLD (project-specific)
   ruff check trend_model tests scripts
   black --check trend_model tests scripts
   
   # NEW (configurable)
   ruff check ${{ inputs.lint-paths }}
   black --check ${{ inputs.format-paths }}
   ```

#### Add Documentation:

```yaml
# Add comprehensive input documentation:
inputs:
  python-versions:
    description: 'JSON array of Python versions to test (e.g., ["3.11", "3.12"])'
    required: false
    default: '["3.11"]'
  coverage-min:
    description: 'Minimum coverage percentage (0-100)'
    required: false
    default: '0'
  package-name:
    description: 'Package name for coverage tracking'
    required: true
  # ... etc
```

### reusable-12-ci-docker.yml

#### Remove/Generalize:

1. **Dockerfile Path:**
   ```yaml
   # OLD (assumed location)
   docker build -f Dockerfile .
   
   # NEW (configurable)
   docker build -f ${{ inputs.dockerfile }} ${{ inputs.context }}
   ```

2. **Image Name:**
   ```yaml
   # OLD (project-specific)
   image: trend-model:test
   
   # NEW (parameterized)
   image: ${{ inputs.image-name }}:${{ inputs.image-tag }}
   ```

3. **Container Tests:**
   ```yaml
   # OLD (project-specific imports)
   docker run trend-model:test python -c "import trend_model"
   
   # NEW (configurable)
   docker run ${{ inputs.image-name }}:${{ inputs.image-tag }} ${{ inputs.smoke-test-command }}
   ```

### reusable-18-autofix.yml

#### Remove/Generalize:

1. **Formatting Tools:**
   ```yaml
   # OLD (Python-specific)
   ruff check --fix
   black .
   isort .
   
   # NEW (configurable tool chain)
   ${{ inputs.format-command }}
   # Or support tool selection:
   # - ruff+black (Python)
   # - prettier (JavaScript)
   # - gofmt (Go)
   # - etc.
   ```

2. **File Patterns:**
   ```yaml
   # OLD (Python files)
   paths: ['**/*.py']
   
   # NEW (configurable)
   paths: ${{ fromJSON(inputs.file-patterns) }}
   ```

3. **Commit Message:**
   ```yaml
   # OLD (project-specific)
   message: '[autofix] Apply formatting (trend_model)'
   
   # NEW (parameterized)
   message: ${{ inputs.commit-message-prefix }} ${{ inputs.commit-message }}
   ```

### health-42-actionlint.yml

#### Remove/Generalize:

1. **Allowlist Path:**
   ```yaml
   # OLD (assumed location)
   cat .github/actionlint-allowlist.txt
   
   # NEW (configurable with default)
   cat ${{ inputs.allowlist-path || '.github/actionlint-allowlist.txt' }}
   ```

2. **Workflow Directory:**
   ```yaml
   # OLD (assumed)
   actionlint .github/workflows/*.yml
   
   # NEW (configurable)
   actionlint ${{ inputs.workflows-path }}/*.yml
   ```

3. **Reporting:**
   ```yaml
   # OLD (reviewer integration specific to project)
   reviewdog integration
   
   # NEW (optional, configurable)
   if: ${{ inputs.enable-reviewdog == 'true' }}
   ```

### maint-52-validate-workflows.yml

#### Remove/Generalize:

1. **Workflow Validation:**
   ```yaml
   # OLD (finds all .yml files)
   for f in .github/workflows/*.yml
   
   # NEW (same, but with configurable path)
   for f in ${{ inputs.workflows-dir || '.github/workflows' }}/*.yml
   ```

2. **Actionlint Configuration:**
   - Same as health-42-actionlint.yml

### pr-00-gate.yml (Template)

#### This file requires the most work to generalize:

1. **Job Configuration:**
   ```yaml
   # OLD (hardcoded job list)
   jobs:
     python-ci:
       uses: ./.github/workflows/reusable-10-ci-python.yml
     docker-smoke:
       uses: ./.github/workflows/reusable-12-ci-docker.yml
     gate:
       needs: [python-ci, docker-smoke]
   
   # NEW (needs to be template-based or config-driven)
   # Option 1: Configuration file
   # Read from .github/gate-config.yml
   # Option 2: Multiple template examples
   # gate-python.yml, gate-node.yml, gate-multi.yml
   ```

2. **Path Filters:**
   ```yaml
   # OLD (project-specific paths)
   paths-ignore:
     - 'docs/**'
     - '**/*.md'
     - 'assets/**'
   
   # NEW (configurable)
   paths-ignore: ${{ inputs.docs-paths }}
   # Or read from config file
   ```

3. **Status Check Names:**
   ```yaml
   # OLD (hardcoded)
   context: "Gate / gate"
   
   # NEW (configurable)
   context: ${{ inputs.gate-context-name }}
   ```

4. **Summary Generation:**
   ```yaml
   # OLD (calls gate_summary.py with project assumptions)
   python .github/scripts/gate_summary.py
   
   # NEW (parameterized)
   python .github/scripts/gate_summary.py \
     --config ${{ inputs.summary-config }} \
     --template ${{ inputs.summary-template }}
   ```

### ci_metrics.py, ci_history.py, ci_coverage_delta.py

#### Remove/Generalize:

1. **Hardcoded Paths:**
   ```python
   # OLD
   ARTIFACT_DIR = Path(".artifact/gate-coverage")
   TEST_DIR = Path("tests")
   
   # NEW (use environment variables or CLI args)
   ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", ".artifact"))
   TEST_DIR = Path(os.getenv("TEST_DIR", "tests"))
   ```

2. **Package Names:**
   ```python
   # OLD
   import trend_model
   coverage_path = "trend_model"
   
   # NEW (configurable)
   package_name = os.getenv("PACKAGE_NAME")
   if package_name:
       coverage_path = package_name
   ```

3. **Metric Calculations:**
   ```python
   # OLD (assumes specific test structure)
   test_files = glob.glob("tests/**/*.py")
   
   # NEW (configurable pattern)
   pattern = os.getenv("TEST_PATTERN", "tests/**/*.py")
   test_files = glob.glob(pattern)
   ```

### autofix/ Action

#### Remove/Generalize:

1. **Tool Detection:**
   ```yaml
   # OLD (assumes Python project)
   runs:
     - name: Run ruff
       run: ruff check --fix .
     - name: Run black
       run: black .
   
   # NEW (detect tools from project)
   runs:
     - name: Detect formatters
       run: |
         if [ -f ".ruff.toml" ] || [ -f "ruff.toml" ]; then
           echo "ruff=true" >> $GITHUB_OUTPUT
         fi
         if [ -f ".prettierrc" ]; then
           echo "prettier=true" >> $GITHUB_OUTPUT
         fi
     - name: Run ruff
       if: steps.detect.outputs.ruff == 'true'
       run: ruff check --fix .
     - name: Run prettier
       if: steps.detect.outputs.prettier == 'true'
       run: prettier --write .
   ```

2. **Configuration Discovery:**
   ```yaml
   # Support multiple config file locations:
   # - pyproject.toml (Python)
   # - .prettierrc (JavaScript)
   # - .editorconfig (Multi-language)
   # - etc.
   ```

### detect-changes.js

#### Remove/Generalize:

1. **Path Classifications:**
   ```javascript
   // OLD (project-specific)
   const DOC_PATHS = ['docs/', 'assets/', '**/*.md'];
   const WORKFLOW_PATHS = ['.github/workflows/'];
   const TEST_PATHS = ['tests/'];
   
   // NEW (configurable)
   const DOC_PATHS = JSON.parse(process.env.DOC_PATHS || '["docs/", "**/*.md"]');
   const WORKFLOW_PATHS = JSON.parse(process.env.WORKFLOW_PATHS || '[".github/workflows/"]');
   const TEST_PATHS = JSON.parse(process.env.TEST_PATHS || '["tests/"]');
   ```

2. **Change Classification Logic:**
   ```javascript
   // Make classification rules configurable via inputs
   // Allow projects to define their own classification schemes
   ```

### gate_summary.py

#### Remove/Generalize:

1. **Artifact Naming:**
   ```python
   # OLD
   COVERAGE_ARTIFACT = "gate-coverage"
   SUMMARY_ARTIFACT = "gate-coverage-summary"
   
   # NEW
   ARTIFACT_PREFIX = os.getenv("ARTIFACT_PREFIX", "ci")
   COVERAGE_ARTIFACT = f"{ARTIFACT_PREFIX}-coverage"
   SUMMARY_ARTIFACT = f"{ARTIFACT_PREFIX}-coverage-summary"
   ```

2. **Summary Template:**
   ```python
   # OLD (hardcoded summary format)
   summary = f"""
   ## Gate Results
   - Python 3.11: {results_311}
   - Python 3.12: {results_312}
   """
   
   # NEW (template-based)
   from jinja2 import Template
   template = Template(open(os.getenv("SUMMARY_TEMPLATE")).read())
   summary = template.render(results=results)
   ```

3. **Status Check Names:**
   ```python
   # OLD
   REQUIRED_CHECKS = ["python-ci", "docker-smoke"]
   
   # NEW
   REQUIRED_CHECKS = json.loads(os.getenv("REQUIRED_CHECKS", "[]"))
   ```

## Documentation Scrubbing

### Remove from Docs:

1. **Issue References:**
   - `Issue #2190`, `Issue #2466`, etc.
   - Replace with generic descriptions of the feature/change

2. **PR References:**
   - `PR #1234`
   - Remove or replace with generic explanation

3. **Workflow Run Links:**
   - `[workflow history](https://github.com/stranske/Trend_Model_Project/actions/workflows/pr-00-gate.yml)`
   - Replace with generic description or placeholder

4. **Project-Specific Context:**
   - References to Trend_Model_Project features
   - References to project history
   - Project-specific terminology

5. **Author/Date Information:**
   - Keep only if relevant to workflow version history
   - Remove project-specific changelog entries

### Generalize in Docs:

1. **Examples:**
   - Replace Trend_Model_Project examples with generic ones
   - Add examples for multiple project types

2. **Configuration:**
   - Document all configurable options
   - Provide sensible defaults
   - Show multiple configuration scenarios

3. **Troubleshooting:**
   - Remove project-specific troubleshooting
   - Add generic troubleshooting for common issues

## Test Scrubbing

### Remove from Tests:

1. **Project-Specific Assertions:**
   ```python
   # OLD
   assert "trend_model" in workflow_content
   assert python_version in ["3.11", "3.12"]
   
   # NEW
   # Remove hard assertions or make them configurable
   ```

2. **Project File References:**
   ```python
   # OLD
   assert Path("tests/test_invariants.py").exists()
   
   # NEW
   # Remove or make test data-driven
   ```

3. **Workflow Name Checks:**
   ```python
   # OLD
   EXPECTED_NAMES = {
       "pr-00-gate.yml": "Gate",
       # ... project-specific names
   }
   
   # NEW
   # Remove project-specific name validation
   # Keep only structural validation
   ```

### Generalize Tests:

1. **Make Tests Data-Driven:**
   ```python
   @pytest.mark.parametrize("workflow_config", [
       {"type": "python", "versions": ["3.11"]},
       {"type": "node", "versions": ["18"]},
   ])
   def test_workflow_matrix(workflow_config):
       # Test with different configurations
   ```

2. **Use Fixtures:**
   ```python
   @pytest.fixture
   def sample_project():
       """Create a minimal project structure for testing"""
       # Generate test project on-the-fly
   ```

## Environment Variables & Secrets

### Remove:

- `SERVICE_BOT_PAT` (project-specific)
- Any project-specific secret names

### Replace With:

- `WORKFLOW_PAT` or `GITHUB_TOKEN` (generic)
- Document required secrets clearly
- Provide fallback behavior when secrets unavailable

## Validation Checklist

Before considering a file "scrubbed":

- [ ] No hardcoded repository name (`stranske/Trend_Model_Project`)
- [ ] No hardcoded branch names (except as defaults)
- [ ] No hardcoded paths (except as defaults)
- [ ] No hardcoded versions (except as defaults)
- [ ] No hardcoded package/module names
- [ ] No project-specific URLs
- [ ] No issue/PR references in code (docs OK if historical)
- [ ] All project-specific logic made configurable
- [ ] Comprehensive input documentation added
- [ ] Default values provided for all optional inputs
- [ ] Tests updated or removed if project-specific
- [ ] Documentation updated with generic examples

## Automation Ideas

### Automated Scrubbing Tools:

1. **Search Script:**
   ```bash
   #!/bin/bash
   # Find all occurrences of project-specific terms
   rg -i "trend.?model" 
   rg -i "stranske"
   rg -i "phase-2-dev"
   rg -i "Issue #[0-9]+"
   ```

2. **Validation Script:**
   ```python
   # Check for common project-specific patterns
   import re
   
   def validate_file(path):
       with open(path) as f:
           content = f.read()
       
       issues = []
       if "stranske" in content.lower():
           issues.append("Contains 'stranske'")
       if "trend_model" in content:
           issues.append("Contains 'trend_model'")
       # ... more checks
       
       return issues
   ```

3. **Template Generator:**
   ```python
   # Convert hardcoded values to template variables
   def templatize(content):
       # Replace known patterns with {{ variables }}
       content = re.sub(
           r'stranske/Trend_Model_Project',
           r'${{ github.repository }}',
           content
       )
       # ... more replacements
       return content
   ```

---

**Document Version**: 1.0  
**Last Updated**: 2024-12-16  
**Status**: Draft - Ready for Review

**Usage**: Use this checklist during extraction process to ensure all project-specific elements are removed or generalized.
