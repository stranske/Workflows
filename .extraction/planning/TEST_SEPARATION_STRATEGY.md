# Test Infrastructure Separation Strategy

## Executive Summary

The Trend_Model_Project repository contains 33+ workflow-related test files already cleanly separated in the `tests/workflows/` directory, along with dedicated fixtures and CI helper scripts. This organization simplifies the transition significantly—workflow tests can be migrated as a cohesive unit with minimal restructuring needed.

## Current State Analysis

### Test Organization (Already Well-Structured)

The source repository has already implemented good test separation:

```
tests/
├── workflows/           # ← ALL workflow-related tests (33+ files)
│   ├── test_workflow_*.py           # Workflow definition tests
│   ├── test_autofix_*.py            # Autofix system tests  
│   ├── test_ci_*.py                 # CI infrastructure tests
│   ├── test_keepalive_*.py          # Keepalive system tests
│   ├── test_agents_*.py             # Agent orchestration tests
│   ├── test_codex_belt_*.py         # Codex belt tests
│   ├── test_reusable_*.py           # Reusable workflow tests
│   ├── github_scripts/              # Tests for .github/scripts/*.js
│   │   ├── test_gate_summary.py
│   │   ├── test_decode_raw_input.py
│   │   ├── test_health_summarize.py
│   │   └── test_fallback_split.py
│   └── fixtures/                    # Workflow test fixtures
│       ├── keepalive/
│       │   ├── harness.js
│       │   └── mock_data/
│       ├── agents_pr_meta/
│       ├── keepalive_post_work/
│       └── orchestrator/
│           └── resolve_harness.js
│
├── fixtures/                        # ← Core test fixtures (NOT workflow-related)
│   └── score_frame_2025-06-30.csv  # Analysis test data
│
├── test_*.py                        # ← Core application tests
├── smoke/                           # Application smoke tests
└── scripts/                         # Tests for project-specific scripts
    ├── test_verify_codex_bootstrap.py
    ├── test_verify_trusted_config.py
    ├── test_sync_tool_versions.py
    └── test_sync_test_dependencies.py
```

**Key Observation**: Workflow tests are already isolated in a dedicated subdirectory, minimizing separation work.

### Test File Inventory

#### Workflow System Tests (33+ files in tests/workflows/)

**Workflow Definition Tests**:
- `test_workflow_naming.py` - Workflow naming conventions
- `test_workflow_agents_consolidation.py` - Agent workflow structure
- `test_workflow_selftest_consolidation.py` - Selftest workflow validation
- `test_workflow_autofix_guard.py` - Autofix guard regression tests
- `test_reusable_ci_workflow.py` - Reusable CI workflow tests

**Autofix System Tests**:
- `test_autofix_*.py` (multiple files) - Autofix automation tests

**CI Infrastructure Tests**:
- `test_ci_metrics.py` - Metrics extraction from JUnit XML
- `test_ci_history.py` - Metrics history tracking
- `test_ci_coverage_delta.py` - Coverage delta computation
- `test_ci_cosmetic_repair.py` - Cosmetic repair workflow

**Keepalive System Tests**:
- `test_keepalive_workflow.py` - Main keepalive workflow tests (~500+ lines)
- `test_keepalive_post_work.py` - Post-execution cleanup tests

**Agent Orchestration Tests**:
- `test_agents_*.py` (multiple files) - Agent system tests

**Codex Belt Tests**:
- `test_codex_belt_*.py` - Codex belt dispatcher/worker tests

**GitHub Scripts Tests** (tests/workflows/github_scripts/):
- `test_gate_summary.py` - Gate summary script tests
- `test_decode_raw_input.py` - Input decoding tests
- `test_health_summarize.py` - Health summary tests
- `test_fallback_split.py` - Fallback split logic tests

**General Automation Tests**:
- `test_automation_workflows.py` - Comprehensive workflow coverage validation

#### CI Helper Scripts (scripts/)

These scripts are tested by the workflow tests and support CI operations:

**Metrics & History**:
- `scripts/ci_metrics.py` - Parse JUnit XML, extract test metrics
- `scripts/ci_history.py` - Append metrics history, generate classification
- `scripts/ci_coverage_delta.py` - Compare coverage vs baseline
- `scripts/ci_feature_assert.py` - Validate CI feature flags

**Cosmetic Repair**:
- `scripts/ci_cosmetic_repair.py` - Auto-fix cosmetic test issues
- `scripts/cosmetic_repair_workflow.py` - Workflow helper for cosmetic repairs

**Test Utilities**:
- `scripts/__init__.py` - Package marker for script imports

**Tests for CI Scripts** (tests/scripts/ - some overlap with tests/workflows/):
- `tests/scripts/test_ci_metrics.py`
- `tests/scripts/test_ci_history.py`
- `tests/scripts/test_ci_coverage_delta.py`

**Note**: Some CI script tests exist in both `tests/scripts/` and `tests/workflows/`. We need to consolidate.

### Node.js Test Infrastructure

**Harness Files** (JavaScript):
- `tests/workflows/fixtures/keepalive/harness.js` - Keepalive test harness
- `tests/workflows/fixtures/orchestrator/resolve_harness.js` - Orchestrator resolver harness

**Purpose**: Execute JavaScript workflow scripts in test context with mocked GitHub API

**Dependencies**:
- Node.js v20+
- npm packages: @actions/core, @actions/github (or @octokit/rest)
- Built-in: fs, path, vm, util

### Test Dependencies

**Python Packages** (required for workflow tests):
- pytest
- pytest-subprocess (for Node.js process mocking)
- yaml (PyYAML) - for workflow YAML parsing
- json - built-in

**Node.js Dependencies**:
- Node.js v20+ runtime
- npm packages (for JavaScript script testing)

## Transition Strategy

### Phase 1: Assessment & Planning (Week 1)

#### 1.1 Test Inventory Audit

**Tasks**:
1. **Verify Test Isolation**:
   - Confirm all 33+ workflow test files reside in `tests/workflows/`
   - Check for any stray workflow tests in root `tests/` directory
   - Identify cross-dependencies with core tests

2. **Dependency Analysis**:
   - Map Python package dependencies (pytest, yaml, etc.)
   - Document Node.js requirements for harness files
   - Identify shared fixtures between workflow and core tests

3. **Coverage Assessment**:
   - Measure current workflow test coverage
   - Identify untested workflow components
   - Document coverage baselines for post-migration validation

**Deliverables**:
- Test inventory spreadsheet
- Dependency matrix
- Coverage baseline report

**Timeline**: 2-3 days

#### 1.2 CI Script Consolidation Planning

**Problem**: Some CI scripts have tests in both `tests/scripts/` and `tests/workflows/`

**Resolution Strategy**:
- **Option A**: Keep all CI script tests in `tests/workflows/` (recommended)
  - Rationale: CI scripts support workflow system
  - Move `tests/scripts/test_ci_*.py` → `tests/workflows/`
  
- **Option B**: Split by script purpose
  - Workflow-specific: `tests/workflows/`
  - General utilities: `tests/scripts/`

**Decision Required**: Choose consolidation approach

**Timeline**: 1 day

### Phase 2: Test Migration (Week 2-3)

#### 2.1 Directory Structure Setup

**Tasks**:
1. Create test directory in Workflows repo:
   ```
   tests/
   ├── workflows/
   │   ├── test_workflow_*.py
   │   ├── test_autofix_*.py
   │   ├── test_ci_*.py
   │   ├── test_keepalive_*.py
   │   ├── test_agents_*.py
   │   ├── test_codex_belt_*.py
   │   ├── test_reusable_*.py
   │   ├── test_automation_workflows.py
   │   ├── github_scripts/
   │   │   ├── __init__.py
   │   │   ├── test_gate_summary.py
   │   │   ├── test_decode_raw_input.py
   │   │   ├── test_health_summarize.py
   │   │   └── test_fallback_split.py
   │   └── fixtures/
   │       ├── keepalive/
   │       │   ├── harness.js
   │       │   └── mock_data/
   │       ├── agents_pr_meta/
   │       ├── keepalive_post_work/
   │       └── orchestrator/
   │           └── resolve_harness.js
   ├── scripts/           # Tests for CI helper scripts
   │   ├── __init__.py
   │   ├── test_ci_metrics.py
   │   ├── test_ci_history.py
   │   ├── test_ci_coverage_delta.py
   │   └── test_cosmetic_repair_workflow.py
   ├── __init__.py
   └── conftest.py        # Shared pytest configuration
   ```

2. Create package markers (`__init__.py`)
3. Set up pytest configuration (`conftest.py`)

**Timeline**: 1 day

#### 2.2 Test File Migration

**Priority**: HIGH
**Timeline**: 5-7 days

**Process**:

**Step 1: Copy Test Files** (Day 1-2)
```bash
# From Trend_Model_Project
cp -r tests/workflows/ /path/to/Workflows/tests/
cp tests/scripts/test_ci_*.py /path/to/Workflows/tests/scripts/
```

**Step 2: Update Import Paths** (Day 3-4)

**Common Path Updates**:
```python
# Before (in Trend_Model_Project)
from scripts import ci_metrics
from scripts import ci_history

# After (in Workflows repo)
from scripts import ci_metrics  # Same if scripts/ is at repo root
from scripts import ci_history
```

**Repository Reference Updates**:
```python
# Before
REPO_ROOT = Path(__file__).resolve().parents[3]  # Goes up to project root
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"

# After  
REPO_ROOT = Path(__file__).resolve().parents[2]  # Adjust depth
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
```

**Step 3: Update Script References in Harness Files** (Day 4-5)

**Example: tests/workflows/fixtures/keepalive/harness.js**
```javascript
// Before
const targetPath = path.resolve(__dirname, '../../../../scripts/keepalive-runner.js');

// After (verify relative path depth)
const targetPath = path.resolve(__dirname, '../../../../scripts/keepalive-runner.js');
// May need adjustment based on final directory structure
```

**Step 4: Update Test Fixtures** (Day 5-6)

- Review fixture data for repository-specific references
- Update mock PR data to reflect generic patterns
- Modify GitHub API mocks for multi-repository scenarios

**Step 5: Update Workflow File Paths** (Day 6-7)

Many tests reference workflow files directly:
```python
# Before
WORKFLOW_PATH = Path(".github/workflows/pr-00-gate.yml")

# After - ensure tests can find workflows
WORKFLOW_PATH = Path(".github/workflows/pr-00-gate.yml")  # Same if structure identical
```

#### 2.3 CI Script Migration

**Priority**: HIGH
**Timeline**: 3-4 days

**Scripts to Migrate**:
1. `scripts/ci_metrics.py` + tests
2. `scripts/ci_history.py` + tests
3. `scripts/ci_coverage_delta.py` + tests
4. `scripts/ci_cosmetic_repair.py` + tests
5. `scripts/cosmetic_repair_workflow.py` + tests
6. `scripts/ci_feature_assert.py`
7. `scripts/__init__.py`

**Process**:
```bash
# Copy CI helper scripts
cp scripts/ci_*.py /path/to/Workflows/scripts/
cp scripts/cosmetic_repair_workflow.py /path/to/Workflows/scripts/
cp scripts/__init__.py /path/to/Workflows/scripts/

# Copy consolidated tests
cp tests/workflows/test_ci_*.py /path/to/Workflows/tests/workflows/
cp tests/scripts/test_ci_*.py /path/to/Workflows/tests/scripts/  # If not consolidated
```

**Updates Needed**:
- No major import path changes (scripts stay in scripts/)
- Update any hardcoded file paths
- Verify logging configuration

### Phase 3: Dependency Management (Week 3-4)

#### 3.1 Python Dependencies

**Tasks**:
1. Create/update `requirements-test.txt`:
   ```
   pytest>=8.0
   pytest-cov>=7.0
   pytest-subprocess>=1.5.0
   PyYAML>=6.0
   ```

2. Create/update `pyproject.toml`:
   ```toml
   [project.optional-dependencies]
   test = [
       "pytest>=8.0",
       "pytest-cov>=7.0",
       "pytest-subprocess>=1.5.0",
       "PyYAML>=6.0",
   ]
   ```

3. Document test installation:
   ```bash
   pip install -e ".[test]"
   # or
   pip install -r requirements-test.txt
   ```

**Timeline**: 1-2 days

#### 3.2 Node.js Dependencies

**Tasks**:
1. Create `package.json`:
   ```json
   {
     "name": "workflows-tests",
     "version": "1.0.0",
     "description": "Test dependencies for workflow system",
     "devDependencies": {
       "@actions/core": "^1.10.0",
       "@actions/github": "^6.0.0"
     },
     "scripts": {
       "test": "pytest tests/workflows/"
     }
   }
   ```

2. Create `.nvmrc` for Node.js version:
   ```
   20
   ```

3. Document setup:
   ```bash
   # Install Node.js dependencies
   npm install
   
   # Or using nvm
   nvm use
   npm install
   ```

**Timeline**: 1 day

### Phase 4: Test Execution & Validation (Week 4-5)

#### 4.1 Local Test Execution

**Priority**: CRITICAL
**Timeline**: 5-7 days

**Process**:

**Day 1-2: Fix Import Issues**
- Run pytest: `pytest tests/workflows/ -v`
- Fix ModuleNotFoundError
- Update sys.path manipulations
- Resolve relative imports

**Day 3-4: Fix Fixture Issues**
- Resolve fixture path problems
- Update mock data references
- Fix harness.js path resolution

**Day 4-5: Fix Test Logic**
- Update repository-specific assertions
- Modify workflow file path checks
- Fix GitHub API mock expectations

**Day 5-6: Node.js Harness Testing**
- Test harness.js in isolation: `node tests/workflows/fixtures/keepalive/harness.js`
- Verify JavaScript script loading
- Fix Node.js module resolution

**Day 6-7: Full Suite Validation**
- Run complete test suite: `pytest tests/ -v`
- Verify 100% pass rate
- Check test coverage: `pytest tests/ --cov=scripts --cov=.github/scripts`

#### 4.2 CI Integration

**Priority**: HIGH
**Timeline**: 3-4 days

**Tasks**:

1. **Create Test Workflow** (`.github/workflows/test.yml`):
   ```yaml
   name: Test Suite
   
   on:
     push:
       branches: [main]
     pull_request:
   
   jobs:
     tests:
       runs-on: ubuntu-latest
       strategy:
         matrix:
           python-version: ['3.11', '3.12']
           node-version: ['20', '22']
       steps:
         - uses: actions/checkout@v4
         
         - uses: actions/setup-python@v5
           with:
             python-version: ${{ matrix.python-version }}
         
         - uses: actions/setup-node@v4
           with:
             node-version: ${{ matrix.node-version }}
         
         - name: Install Python dependencies
           run: |
             pip install --upgrade pip
             pip install -e ".[test]"
         
         - name: Install Node.js dependencies
           run: npm install
         
         - name: Run workflow tests
           run: pytest tests/workflows/ -v --cov=scripts --cov=.github/scripts
         
         - name: Run CI script tests
           run: pytest tests/scripts/ -v
         
         - name: Upload coverage
           uses: codecov/codecov-action@v4
           if: matrix.python-version == '3.11' && matrix.node-version == '20'
   ```

2. **Configure Coverage**:
   - Set coverage minimum threshold
   - Configure coverage reporting
   - Set up Codecov integration (optional)

3. **Add Status Badges**:
   ```markdown
   # Workflows
   
   ![Tests](https://github.com/stranske/Workflows/workflows/Test%20Suite/badge.svg)
   ![Coverage](https://codecov.io/gh/stranske/Workflows/branch/main/graph/badge.svg)
   ```

### Phase 5: Documentation (Week 5)

#### 5.1 Testing Documentation

**Priority**: HIGH
**Timeline**: 2-3 days

**Create**: `docs/testing/README.md`

**Content**:
```markdown
# Testing Guide

## Overview
This repository contains comprehensive tests for the workflow system.

## Test Structure
- `tests/workflows/` - Workflow system tests
- `tests/scripts/` - CI helper script tests
- `tests/workflows/fixtures/` - Test fixtures and harnesses

## Running Tests

### Prerequisites
- Python 3.11+
- Node.js 20+
- pytest and test dependencies

### Installation
\`\`\`bash
pip install -e ".[test]"
npm install
\`\`\`

### Run All Tests
\`\`\`bash
pytest tests/ -v
\`\`\`

### Run Specific Test Categories
\`\`\`bash
# Workflow tests only
pytest tests/workflows/ -v

# CI script tests only
pytest tests/scripts/ -v

# Keepalive tests
pytest tests/workflows/test_keepalive*.py -v

# With coverage
pytest tests/ --cov=scripts --cov=.github/scripts
\`\`\`

## Test Fixtures

### Keepalive Harness
Located in `tests/workflows/fixtures/keepalive/harness.js`.
Provides Node.js harness for testing JavaScript workflow scripts.

### Mock Data
Sample PR data, comments, and API responses for testing.

## Writing Tests

### Python Tests
Follow pytest conventions...

### Node.js Harness Tests
How to use the harness...

## CI Integration
Tests run automatically on push and PR...
\`\`\`

#### 5.2 Developer Guide Updates

**Create**: `docs/development/CONTRIBUTING.md`

**Content**:
- How to run tests locally
- Test coverage requirements
- Adding new tests
- Debugging test failures
- CI integration

**Timeline**: 1-2 days

## Challenges & Solutions

### Challenge 1: Repository-Specific References

**Problem**: Tests contain hardcoded paths to Trend_Model_Project workflows, scripts, and fixtures.

**Solution**:
- Use relative paths from test file locations
- Parameterize repository references where applicable
- Create environment variable overrides for test paths

**Implementation**:
```python
# Generic path resolution
REPO_ROOT = Path(__file__).resolve().parents[2]  # Adjust as needed
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SCRIPT_DIR = REPO_ROOT / "scripts"
```

### Challenge 2: Node.js Harness Complexity

**Problem**: JavaScript harness files use complex module loading and VM contexts.

**Solution**:
- Keep harness architecture unchanged (it works well)
- Update only path references
- Add comprehensive comments
- Create harness usage documentation

### Challenge 3: Mock Data Maintenance

**Problem**: Mock data (PR info, comments, API responses) may need updates for new scenarios.

**Solution**:
- Create mock data factory functions
- Parameterize mock objects
- Version mock data fixtures
- Document mock data schema

**Example**:
```python
def create_mock_pr(number=1, state="open", author="test-user", labels=None):
    """Create mock PR data for testing."""
    return {
        "number": number,
        "state": state,
        "user": {"login": author},
        "labels": labels or [],
        # ... more fields
    }
```

### Challenge 4: CI Script Import Patterns

**Problem**: CI scripts use dynamic imports and module detection.

**Solution**:
- Test both import patterns:
  ```python
  try:
      from scripts import ci_metrics
  except ModuleNotFoundError:
      import ci_metrics  # Fallback for script execution
  ```
- Ensure scripts/ is on sys.path in test environment
- Use pytest fixtures to set up import environment

### Challenge 5: Coverage Measurement

**Problem**: Coverage tools may not accurately measure JavaScript harness usage.

**Solution**:
- Focus Python coverage on test files and Python scripts
- Document JavaScript coverage gaps
- Consider Istanbul/nyc for JavaScript coverage (future enhancement)
- Set realistic coverage targets (80% for Python, document JS as unmeasured)

## Success Criteria

### Phase Completion Checks

**Phase 1 Complete**:
- [ ] Test inventory documented (33+ files accounted for)
- [ ] Dependency matrix created
- [ ] CI script consolidation plan finalized
- [ ] Coverage baseline established

**Phase 2 Complete**:
- [ ] All 33+ workflow test files migrated
- [ ] Test directory structure created
- [ ] Import paths updated
- [ ] Fixture paths corrected
- [ ] Harness files functional

**Phase 3 Complete**:
- [ ] Python test dependencies installed
- [ ] Node.js dependencies configured
- [ ] requirements-test.txt created
- [ ] package.json created

**Phase 4 Complete**:
- [ ] All tests pass locally (100%)
- [ ] CI workflow executes successfully
- [ ] Coverage measured and baseline set
- [ ] No test execution errors

**Phase 5 Complete**:
- [ ] Testing documentation complete
- [ ] Developer guide updated
- [ ] Test examples provided
- [ ] Troubleshooting guide available

### Overall Success Metrics

**Quantitative**:
- [ ] 100% of workflow tests migrated (33+ files)
- [ ] 100% test pass rate
- [ ] Coverage ≥80% for Python code
- [ ] Zero test execution errors in CI
- [ ] CI job completion time <10 minutes

**Qualitative**:
- [ ] Tests are maintainable (clear, documented)
- [ ] Developer can run tests locally easily
- [ ] CI integration is stable
- [ ] Documentation is comprehensive

## Timeline Summary

| Phase | Duration | Critical Path | Dependencies |
|-------|----------|---------------|--------------|
| Phase 1: Assessment | 1 week | Yes | None |
| Phase 2: Migration | 2 weeks | Yes | Phase 1 |
| Phase 3: Dependencies | 1 week | No | Phase 2 |
| Phase 4: Validation | 1-2 weeks | Yes | Phase 2, 3 |
| Phase 5: Documentation | 1 week | No | Phase 4 |
| **Total** | **5-7 weeks** | | |

**Critical Path**: Phases 1 → 2 → 4 (minimum 4-5 weeks)

**Parallel Work Opportunities**:
- Documentation (Phase 5) can start during Phase 4
- Dependency setup (Phase 3) can overlap with late Phase 2

## Post-Migration Maintenance

### Regular Tasks

**After Each Workflow Addition**:
- Add corresponding tests
- Update test fixtures
- Verify CI passes
- Update test documentation

**Monthly**:
- Review test coverage
- Update mock data fixtures
- Refactor slow tests
- Review test execution time

**Quarterly**:
- Audit test dependencies
- Update testing guide
- Review CI job performance
- Assess test organization

### Continuous Improvement

**Future Enhancements**:
- JavaScript code coverage (Istanbul/nyc)
- Performance benchmarks for tests
- Parallel test execution
- Test result dashboards
- Automated mock data generation

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX  
**Status**: Draft - Ready for Review
