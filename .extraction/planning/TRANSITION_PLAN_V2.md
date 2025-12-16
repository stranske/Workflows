# Workflow System Extraction - Comprehensive Transition Plan v2.0

## Executive Summary

This plan details the extraction of the GitHub Actions workflow system from the [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project) repository into this standalone Workflows repository. The goal is to create a reusable, project-agnostic workflow system that other repositories can consume.

**Timeline**: 12-16 weeks (December 2024 - March 2025)  
**Date**: December 16, 2024  
**Status**: Planning Phase - Comprehensive Research Complete  
**Version**: 2.0 - Catalytic Ordering with Evaluation Gates

### Core Principles

1. **Catalytic Ordering**: Phases ordered for maximum enabling effect - foundation components that accelerate all subsequent work come first
2. **Evaluation Over Automation**: Always move a file, then evaluate for workflow appropriateness, then optimize for independence
3. **Quality Over Quantity**: Thoughtful extraction beats mechanical copying
4. **Preliminary Audit**: Identify organizational patterns before recreating them

### Key Expansion Areas

Following comprehensive research, four major subsystems have been identified requiring dedicated transition strategies:

1. **Virtual Environment & Validation System** (6 weeks) - Tiered validation enabling rapid feedback (2-5s to 120s)
2. **Test Infrastructure** (5-7 weeks) - 33+ workflow test files with Node.js harnesses  
3. **Keepalive System** (5-8 weeks) - Sophisticated PR automation framework (~1,500 lines JavaScript)
4. **Documentation Filtering** (6 weeks) - ~100+ files requiring evaluation (23 immediate, 15 filter, 50+ exclude)

### Catalytic Phase Ordering

**Foundation → Structure → Functionality → Sophistication**

```
Phase 0: Documentation Audit (Week 1)
  ↓ Enables: Informed organizational decisions
  
Phase 1: Virtual Environment (Weeks 2-3)  
  ↓ Enables: Rapid development feedback (2-5s validation)
  
Phase 2: Documentation Framework (Weeks 3-4)
  ↓ Enables: Consistent structure for all documentation
  
Phase 3: Test Infrastructure (Weeks 4-6)
  ↓ Enables: Validation-driven workflow migration
  
Phase 4: Core Workflows (Weeks 7-9)
  ↓ Enables: Basic workflow consumption
  
Phase 5: Keepalive System (Weeks 10-13)
  ↓ Enables: Advanced automation capabilities
  
Phases 6-10: Remaining systems, integration, release (Weeks 14-16)
```

---

## Current State Analysis

### Source Repository: Trend_Model_Project

**36 Active Workflows** organized by function:

- **PR Checks** (2): Gate orchestration, smoke tests
- **Reusable Workflows** (5): Python CI, Docker CI, autofix, agents, issue bridge
- **Health Checks** (8): Actionlint, sweep, repo health, security, branch protection, agent guard
- **Maintenance** (10): Cosmetic repair, post-CI, dependency refresh, workflow validation, release, coverage guard, legacy cleanup, tool version check
- **Agents/Automation** (11): Issue intake, orchestrator, codex belt system, PR metadata, keepalive system, debug

**Supporting Infrastructure**:

- **Actions** (4): autofix/, build-pr-comment/, codex-bootstrap-lite/, signature-verify/
- **Scripts**: 50+ supporting scripts in .github/scripts/, scripts/, tools/
- **Tests**: 33+ workflow test files in tests/workflows/ with Node.js harnesses
- **Documentation**: ~100+ files across docs/ci/, docs/workflows/, docs/keepalive/, docs/agents/

### Subsystem Research Complete

Four comprehensive planning documents created:

1. **`.extraction/planning/KEEPALIVE_TRANSITION.md`**
   - 5-8 week plan for ~1,500-line JavaScript automation system
   - Components: keepalive-runner.js (1,065 lines), 4 helper scripts, 3+ workflows, tests
   - 5-phase strategy: Foundation → Workflow Integration → Documentation → Tests → Validation

2. **`.extraction/planning/TEST_SEPARATION_STRATEGY.md`**
   - 5-7 week plan for test infrastructure (33+ files)
   - Key finding: Tests already well-separated in tests/workflows/
   - 5-phase strategy: Assessment → Migration → Dependencies → Execution → Documentation

3. **`.extraction/planning/VIRTUAL_ENVIRONMENT_TRANSITION.md`**
   - 6-week plan for tiered validation system
   - Three tiers: dev_check.sh (2-5s), validate_fast.sh (5-30s), check_branch.sh (30-120s)
   - 6-phase strategy: Foundation → Git Hooks → Devcontainer → Docs → Testing → CI Integration

4. **`.extraction/planning/DOCS_FILTERING_MATRIX.md`**
   - 6-week plan for documentation transition
   - Three tiers: IMMEDIATE (23 files), FILTER REQUIRED (15 files), EXCLUDE (50+ files)
   - File-by-file transition matrix with extraction strategies

---

## Phase 0: Preliminary Documentation Audit (Week 1)

### Objectives

**Do NOT mechanically copy documentation structure** - First understand what exists and what organizational patterns should be preserved or avoided.

**Scan for**:
1. Organizational hierarchies (folder structures, naming conventions)
2. Document types and templates (goal-plumbing patterns, reliability plans, observability contracts)
3. Structural conventions (terminology, linking patterns, metadata formats)
4. Anti-patterns (runtime status tracking, project-specific coupling)

### Deliverables

1. **`DOCUMENTATION_AUDIT.md`** in `.extraction/planning/` containing:
   - Complete inventory of docs/ structure
   - Document type taxonomy with examples
   - Template library (3-5 reusable structures)
   - Anti-patterns to avoid (what NOT to recreate)
   - Recommended docs/ architecture for Workflows repo

2. **Architectural Baseline**:
   - Proposed folder structure
   - Document quality standards
   - Template usage guidelines
   - Linking conventions

### Tasks

**Week 1**:
```bash
# 1. Scan documentation structure
find docs/ -type f -name "*.md" | sort > .extraction/docs_inventory.txt

# 2. Analyze organizational patterns
# - Document types (guides vs references vs plans vs status)
# - Hierarchy depth and rationale
# - Cross-linking patterns

# 3. Extract templates
# - Identify repeated document structures
# - Document template components
# - Create template library

# 4. Identify anti-patterns
# - Runtime status files (RUNTIME_STATUS.md)
# - Project-specific coupling
# - Organizational duplication
```

### Evaluation Criteria

**Phase complete when**:
- ✅ All docs/ scanned (100+ files cataloged)
- ✅ Organizational patterns documented (hierarchies, naming, linking)
- ✅ Template library created (3-5 reusable structures)
- ✅ Anti-patterns identified (what NOT to recreate)
- ✅ Architectural baseline provides clear guidance

**Evaluation Gate**: Audit must answer "What organizational elements exist that we should preserve?" and "What should we avoid recreating?"

---

## Phase 1: Virtual Environment & Validation System (Weeks 2-3)

### Rationale: Maximum Catalytic Effect

The validation system is prioritized because it:
- **Enables all subsequent development** with rapid feedback loops
- **Improves productivity immediately** (2-5s validation vs minutes)
- **Required by all phases** for testing workflow transitions
- **Foundational dependency** for CI/CD integration

### Architecture: Three-Tier Validation

**Tier 1 - Ultra-Fast (2-5s)**: `dev_check.sh`
- Syntax checking
- Import validation
- Basic linting
- Perfect for pre-commit

**Tier 2 - Adaptive (5-30s)**: `validate_fast.sh`
- Intelligent scope detection
- Adaptive test selection
- Quick feedback for iterative development

**Tier 3 - Comprehensive (30-120s)**: `check_branch.sh`
- Full test suite
- Complete coverage analysis
- Pre-merge validation

### Week 2: Foundation Scripts

**Tasks**:

1. **Copy validation scripts**:
   ```bash
   cp scripts/dev_check.sh → scripts/dev_check.sh
   cp scripts/validate_fast.sh → scripts/validate_fast.sh
   cp scripts/check_branch.sh → scripts/check_branch.sh
   ```

2. **EVALUATE each script** (DO NOT skip this step):
   - ❌ Remove: Project-specific paths (tests/test_invariants.py, trend_model/, etc.)
   - ❌ Remove: Hardcoded repository references
   - ✅ Preserve: Validation logic, timing targets, error handling
   - ✅ Generalize: Python/Node detection, path discovery

3. **OPTIMIZE for independence**:
   - Parameterize project-specific elements
   - Add configuration file support
   - Document tier selection guidelines

4. **Test execution**:
   ```bash
   ./scripts/dev_check.sh      # Must complete in 2-5s
   ./scripts/validate_fast.sh  # Must complete in 5-30s
   ./scripts/check_branch.sh   # Must complete in 30-120s
   ```

5. **Copy tool version sync**:
   ```bash
   cp .github/workflows/autofix-versions.env → .github/workflows/autofix-versions.env
   cp scripts/sync_tool_versions.py → scripts/sync_tool_versions.py
   ```

6. **EVALUATE sync infrastructure**:
   - ❌ Remove: Project-specific tool versions
   - ✅ Preserve: Sync mechanism, validation logic
   - ✅ Generalize: Make version specifications configurable

**Evaluation Gate - Week 2**:
- ✅ All three scripts execute successfully
- ✅ No project-specific hardcoded paths remain
- ✅ Timing targets met (2-5s, 5-30s, 30-120s)
- ✅ Tool version sync verified functional
- ✅ Each script individually evaluated and optimized

### Week 3: Integration & Environment

**Tasks**:

1. **Copy git hooks**:
   ```bash
   cp scripts/git_hooks.sh → scripts/git_hooks.sh
   ```

2. **EVALUATE git hooks**:
   - ❌ Remove: Project-specific hook configurations
   - ✅ Preserve: Hook installation/uninstallation logic
   - ✅ Verify: References to validation scripts are correct
   - Test: `./scripts/git_hooks.sh install` and trigger validation

3. **Copy devcontainer**:
   ```bash
   cp .devcontainer/ → .devcontainer/
   ```

4. **EVALUATE devcontainer**:
   - ❌ Remove: Project-specific VS Code extensions (trend_model specific)
   - ❌ Remove: Project-specific environment variables
   - ✅ Preserve: Python 3.11+ and Node.js 20+ requirements
   - ✅ Preserve: Essential workflow development extensions
   - Test: Rebuild devcontainer and verify environment

5. **Copy environment setup**:
   ```bash
   cp scripts/setup_env.sh → scripts/setup_env.sh
   ```

6. **EVALUATE setup script**:
   - ❌ Remove: Project-specific package installations
   - ✅ Preserve: Environment bootstrapping logic (60-180s target)
   - ✅ Generalize: Python/Node version detection
   - Test: Fresh environment setup

7. **Create documentation**:
   - Extract workflow-relevant portions from `docs/fast-validation-ecosystem.md` (~80% applicable)
   - **EVALUATE paragraph-by-paragraph**: Keep validation system documentation, remove project-specific usage examples
   - **OPTIMIZE**: Rewrite for generic workflow development context
   - Create: `docs/validation-system.md` with tier selection guide

**Evaluation Gate - Week 3**:
- ✅ Devcontainer builds successfully in < 5 minutes
- ✅ Git hooks install and trigger correct validation tier
- ✅ Setup script creates working environment (60-180s target)
- ✅ Documentation complete for all three tiers
- ✅ All components evaluated individually for appropriateness
- ✅ No project-specific configuration remains

**Reference**: Complete implementation details in `.extraction/planning/VIRTUAL_ENVIRONMENT_TRANSITION.md`

---

## Phase 2: Documentation Framework (Weeks 3-4)

### Rationale: Structure Enables Consistency

Establishing documentation organization early:
- **Provides consistent structure** for all subsequent documentation
- **Templates guide creation** during workflow transitions
- **Prevents duplication** of organizational patterns from audit
- **Enables quality validation** of documentation completeness

### Week 3: Immediate Content Transition (23 Files)

**Category: IMMEDIATE TIER** (from DOCS_FILTERING_MATRIX.md)

Files ready for direct transition - 100% workflow-relevant:

```
docs/ci/WORKFLOWS.md
docs/ci/WORKFLOW_SYSTEM.md
docs/ci/gate-workflow-design.md
docs/ci/reusable-ci-design.md
docs/ci/workflow-patterns.md
docs/workflows/*.md (entire directory)
docs/keepalive/*.md (except RUNTIME_STATUS.md)
docs/agents/agents-system-overview.md (workflow portions)
docs/agents/agents-workflow-integration.md
docs/testing/workflow-testing-guide.md
```

**Process** (DO NOT batch - evaluate individually):

For each file:
1. **Copy file** to appropriate location in Workflows repo
2. **READ the entire file** - understand content before editing
3. **EVALUATE line-by-line**:
   - ❌ Remove: stranske/Trend_Model_Project references
   - ❌ Remove: Project-specific paths, examples, configurations
   - ❌ Remove: Links to project-specific issues/PRs
   - ✅ Preserve: Workflow system architecture, patterns, design decisions
   - ✅ Preserve: Reusable examples (parameterized)
4. **OPTIMIZE for independence**:
   - Replace hardcoded values with `<PROJECT>` placeholders
   - Generalize examples to show patterns not specifics
   - Update internal links to new structure
5. **VALIDATE**:
   - Test all internal links
   - Verify code examples are syntactically correct
   - Check markdown formatting
   - Ensure document is coherent and complete

**Evaluation Gate - Week 3**:
- ✅ All 23 immediate files transitioned
- ✅ Each file evaluated individually (not batch copied)
- ✅ No project-specific references remain
- ✅ Internal links functional
- ✅ Code examples validated
- ✅ Document quality verified against standards from Phase 0 audit

### Week 4: Filtered Content Extraction (15 Files)

**Category: FILTER REQUIRED TIER** (from DOCS_FILTERING_MATRIX.md)

Files containing mixed content - extraction required:

```
docs/fast-validation-ecosystem.md (80% workflow, 20% project)
docs/directory-index/scripts.md (60% workflow, 40% project)
docs/ops/codex-bootstrap-facts.md (workflow portions only)
docs/ops/GHA_and_codex_tips.md (workflow-specific tips only)
docs/developer/environment-setup.md (workflow dev portions)
...15 files total
```

**Process** (Thoughtful extraction, not mechanical):

For each file:
1. **Open source file** in Trend_Model_Project
2. **Read completely** - understand full context
3. **EVALUATE paragraph-by-paragraph**:
   - ✅ Extract: Workflow system concepts, patterns, best practices
   - ✅ Extract: Generic development guidance applicable to workflows
   - ❌ Skip: Project-specific implementation details
   - ❌ Skip: References to project structure/modules
   - ❌ Skip: Project-specific troubleshooting
4. **REWRITE extracted content**:
   - Don't just copy paragraphs - rewrite for clarity and independence
   - Combine related sections for better flow
   - Add context where project-specific context is removed
   - Ensure extracted content stands alone
5. **OPTIMIZE structure**:
   - May need to reorganize compared to source
   - May need to split into multiple documents
   - May need to combine with content from other sources
6. **VALIDATE coherence**:
   - Read the new document start to finish
   - Ensure logical flow without gaps
   - Verify examples are complete and correct
   - Check against documentation standards from Phase 0

**Example: docs/fast-validation-ecosystem.md**
- **Extract**: Tier 1/2/3 validation concepts, timing targets, usage patterns
- **Skip**: Specific tests for trend_model modules, project file listings
- **Rewrite**: "Testing trend_model.core takes 5s" → "Testing your project's core modules should target <5s"
- **Result**: `docs/validation-system.md` (created in Phase 1)

**Evaluation Gate - Week 4**:
- ✅ All 15 filter-required files processed
- ✅ Extracted content verified workflow-appropriate
- ✅ No mechanical paragraph copying - content rewritten for independence
- ✅ New documents coherent and complete
- ✅ Document structure improved where needed (not just copied)
- ✅ Quality verified against Phase 0 standards

**Reference**: Complete file-by-file transition matrix in `.extraction/planning/DOCS_FILTERING_MATRIX.md`

---

## Phase 3: Test Infrastructure (Weeks 4-6)

### Rationale: Enable Validation-Driven Development

Test infrastructure enables:
- **Validation of all workflow transitions** with confidence
- **Regression prevention** during generalization refactoring
- **Quality gates** for subsequent phases
- **CI/CD foundation** for workflow system itself

### Key Finding: Clean Existing Separation

Research revealed tests are **already well-separated** in `tests/workflows/` directory (33+ files) - this significantly simplifies the transition compared to initially expected "bigger challenge".

**Current Organization**:
```
tests/workflows/
  test_workflow_*.py          # Workflow integration tests
  test_autofix_*.py           # Autofix system tests  
  test_ci_*.py                # CI helper script tests
  test_keepalive_*.py         # Keepalive system tests
  test_agents_*.py            # Agent workflow tests
  github_scripts/             # Script unit tests
  fixtures/                   # Test data & Node.js harnesses
    keepalive/
    agents_pr_meta/
    orchestrator/
    harness.js files          # JavaScript execution in test context
```

### Week 4-5: Test File Migration & Evaluation

**Tasks**:

1. **Copy test directory**:
   ```bash
   cp -r tests/workflows/ → tests/workflows/
   ```

2. **EVALUATE each test file** (33+ files - systematic review):

   For each `test_*.py` file:
   - **READ the test file** completely
   - **EVALUATE test cases**:
     - ❌ Remove: Tests of project-specific behavior (trend_model imports, invariant tests)
     - ❌ Remove: Assertions about project-specific values
     - ✅ Preserve: Tests of workflow logic, script behavior, validation systems
     - ✅ Preserve: Tests of reusable patterns
   - **UPDATE imports**:
     - Change project-specific imports to workflow-appropriate
     - Fix relative paths if directory structure changed
     - Verify all imports resolve
   - **OPTIMIZE test logic**:
     - Parameterize hardcoded values
     - Generalize assertions where appropriate
     - Add configuration for project-specific elements
   - **Test execution**:
     ```bash
     pytest tests/workflows/test_<specific_file>.py -v
     ```

3. **EVALUATE test fixtures** (fixtures/ directory):
   - **Scan all fixture files** in keepalive/, agents_pr_meta/, orchestrator/
   - ❌ Remove: Project-specific test data (file paths, module names, specific issues)
   - ✅ Preserve: Fixture structure and format
   - ✅ Generalize: Use placeholder values, make configurable
   - **Update harness.js files**:
     - Verify script paths referenced are correct
     - Update @actions/core and @actions/github imports
     - Test Node.js execution in test context

4. **EVALUATE github_scripts/ tests**:
   - Review tests for .github/scripts/ helper scripts
   - Remove tests of project-specific script behavior
   - Update tests for generalized script versions

**Evaluation Gate - Week 5**:
- ✅ All 33+ test files copied and evaluated individually
- ✅ Project-specific test cases removed or generalized
- ✅ All import paths updated and verified
- ✅ Test fixtures verified appropriate
- ✅ Node.js harnesses functional
- ✅ Individual test files pass: `pytest tests/workflows/test_*.py`

### Week 5-6: Dependencies & Full Suite Validation

**Tasks**:

1. **Create Python test dependencies**:
   ```bash
   # Create requirements-test.txt
   echo "pytest>=7.0" > requirements-test.txt
   echo "pytest-subprocess>=1.5" >> requirements-test.txt
   echo "PyYAML>=6.0" >> requirements-test.txt
   ```

2. **EVALUATE dependencies**:
   - ❌ Remove: Project-specific test dependencies
   - ✅ Keep: Core testing framework (pytest)
   - ✅ Keep: Workflow testing tools (pytest-subprocess for subprocess mocking)
   - ✅ Keep: Minimal set only
   - Test: `pip install -r requirements-test.txt`

3. **Create Node.js test dependencies**:
   ```json
   {
     "name": "workflows-tests",
     "version": "1.0.0",
     "devDependencies": {
       "@actions/core": "^1.10.0",
       "@actions/github": "^5.1.1"
     }
   }
   ```

4. **EVALUATE Node dependencies**:
   - Verify minimal set for harness.js execution
   - Test: `npm install && node tests/workflows/fixtures/*/harness.js`

5. **Copy CI helper scripts**:
   ```bash
   cp scripts/ci_metrics.py → scripts/ci_metrics.py
   cp scripts/ci_history.py → scripts/ci_history.py
   cp scripts/ci_coverage_delta.py → scripts/ci_coverage_delta.py
   ```

6. **EVALUATE CI scripts** (DO NOT skip):
   - **READ each script** completely
   - ❌ Remove: Project-specific metric collection
   - ❌ Remove: Hardcoded paths, file names, thresholds
   - ✅ Preserve: Parsing logic (JUnit XML, coverage JSON)
   - ✅ Preserve: Metrics calculation algorithms
   - ✅ Generalize: Parameterize thresholds, paths, configurations
   - Test: Run scripts against sample test results

7. **Run full test suite**:
   ```bash
   pytest tests/workflows/ -v --tb=short
   ```

8. **Fix all failures**:
   - Address import errors
   - Fix fixture path issues
   - Update test assertions
   - Generalize test logic
   - **Target: 100% pass rate**

9. **Create documentation**:
   - `docs/testing/TESTING_GUIDE.md`:
     - How to run tests
     - Test structure and organization
     - Writing new workflow tests
     - Node.js harness usage
     - CI integration

**Evaluation Gate - Week 6**:
- ✅ Full test suite passes (100% pass rate required)
- ✅ Dependencies minimal and documented
- ✅ CI helper scripts generalized and functional
- ✅ Testing guide complete with examples
- ✅ Node.js harness testing validated
- ✅ CI integration documented
- ✅ All components evaluated for workflow appropriateness

**Reference**: Complete test separation strategy in `.extraction/planning/TEST_SEPARATION_STRATEGY.md`

---

## Phase 4: Core Reusable Workflows (Weeks 7-9)

### Rationale: Foundation Workflow Functionality

With validation system and tests in place, core workflows can be transitioned with confidence:
- **Validation in 2-5s** enables rapid iteration
- **Tests validate** workflow behavior during generalization
- **Documentation framework** structures workflow guides

### Workflow Categories

**Week 7-8: Reusable Workflows**
```
.github/workflows/reusable-10-ci-python.yml
.github/workflows/reusable-12-ci-docker.yml
.github/workflows/reusable-18-autofix.yml
```

**Week 8-9: Health & Maintenance**
```
.github/workflows/health-42-actionlint.yml
.github/workflows/health-40-sweep.yml
.github/workflows/maint-52-validate-workflows.yml
.github/workflows/maint-60-release.yml
```

### Process for Each Workflow

**DO NOT batch - evaluate individually**:

1. **Copy workflow file**:
   ```bash
   cp .github/workflows/<workflow>.yml → .github/workflows/<workflow>.yml
   ```

2. **EVALUATE workflow** (READ the entire file):
   - ❌ Remove: Repository-specific references (stranske/Trend_Model_Project)
   - ❌ Remove: Hardcoded branch names (main, phase-2-dev)
   - ❌ Remove: Project-specific paths, test files, coverage targets
   - ❌ Remove: Project-specific secrets (SERVICE_BOT_PAT)
   - ✅ Preserve: Workflow logic, job structure, reusable patterns
   - ✅ Preserve: Error handling, artifact management, status reporting

3. **OPTIMIZE for reusability**:
   - **Parameterize** repository-specific values:
     ```yaml
     inputs:
       repository:
         description: 'Repository name'
         required: true
       python-versions:
         description: 'Python versions to test'
         default: '["3.11", "3.12"]'
       coverage-min:
         description: 'Minimum coverage percentage'
         default: '80'
     ```
   - **Generalize** job steps:
     - Use workflow inputs instead of hardcoded values
     - Make paths configurable
     - Allow override of defaults
   - **Document** inputs and outputs:
     - Clear descriptions
     - Sensible defaults
     - Usage examples

4. **EVALUATE supporting files**:
   - Copy and evaluate any referenced actions (`.github/actions/`)
   - Copy and evaluate any referenced scripts (`.github/scripts/`)
   - Apply same evaluation process: remove project-specific, preserve logic, optimize for reuse

5. **Test workflow**:
   ```bash
   # Validate syntax
   actionlint .github/workflows/<workflow>.yml
   
   # Test execution (if reusable)
   # Create test caller workflow
   # Execute and verify behavior
   ```

6. **Create documentation**:
   - For each workflow, create or update `docs/workflows/<workflow-name>.md`:
     - Purpose and use cases
     - Input parameters
     - Output artifacts
     - Usage examples
     - Integration patterns

**Evaluation Gate - Per Workflow**:
- ✅ Workflow file evaluated line-by-line
- ✅ No project-specific references remain
- ✅ All inputs documented with defaults
- ✅ Supporting files evaluated and optimized
- ✅ Syntax validated (actionlint passes)
- ✅ Execution tested (if reusable workflow)
- ✅ Documentation complete with examples

**Evaluation Gate - Phase Complete**:
- ✅ All core workflows transitioned
- ✅ Each workflow individually evaluated
- ✅ Full reusability test (can be consumed by external repository)
- ✅ Documentation complete
- ✅ Examples validated

---

## Phase 5: Keepalive System (Weeks 10-13)

### Rationale: Advanced Automation

Keepalive system represents sophisticated automation - requires:
- **Solid foundation** from previous phases (validation, tests, core workflows)
- **Careful evaluation** due to complexity (~1,500 lines JavaScript)
- **Cross-repository integration** patterns

### System Overview

**Core Components**:
- `scripts/keepalive-runner.js` (~1,065 lines) - Main orchestration
- Helper scripts: keepalive_gate.js, keepalive_post_work.js, agents_pr_meta_keepalive.js
- Workflows: agents-70-orchestrator.yml (keepalive sweep), agents-keepalive-branch-sync.yml, agents-keepalive-dispatch-handler.yml
- Templates: .github/keepalive-pr-template.md
- Tests: test_keepalive_workflow.py with Node.js harness
- Documentation: docs/keepalive/ (10+ files)

### Week 10-11: Foundation Scripts & Evaluation

**Tasks**:

1. **Copy keepalive-runner.js**:
   ```bash
   cp scripts/keepalive-runner.js → scripts/keepalive-runner.js
   ```

2. **EVALUATE keepalive-runner.js** (1,065 lines - thorough review required):
   - **READ the entire script** - understand architecture before editing
   - **Function-by-function evaluation**:
     - `runKeepalive()`: ❌ Remove project-specific PR patterns, ✅ Preserve orchestration logic
     - `dispatchKeepaliveCommand()`: ✅ Preserve dispatch pattern, ❌ Remove hardcoded workflow refs
     - `extractScopeTasksAcceptanceSections()`: ✅ Preserve parsing, make format configurable
     - `buildTraceToken()`: ✅ Preserve (generic)
   - **OPTIMIZE for cross-repository use**:
     - Parameterize repository references
     - Make state file locations configurable
     - Externalize PR template patterns
     - Add configuration file support
   - **Test Node.js 20+ compatibility**:
     ```bash
     node scripts/keepalive-runner.js --help
     ```

3. **Copy and EVALUATE helper scripts**:
   ```bash
   cp scripts/keepalive_gate.js → scripts/keepalive_gate.js
   cp scripts/keepalive_post_work.js → scripts/keepalive_post_work.js
   cp scripts/agents_pr_meta_keepalive.js → scripts/agents_pr_meta_keepalive.js
   ```
   
   For each script:
   - **READ completely**
   - ❌ Remove: Project-specific validation rules
   - ✅ Preserve: Pre/post execution patterns
   - ✅ Generalize: Make rules configurable

4. **Copy PR template**:
   ```bash
   cp .github/keepalive-pr-template.md → .github/keepalive-pr-template.md
   ```

5. **EVALUATE template**:
   - ❌ Remove: Project-specific sections
   - ✅ Preserve: Template structure, scope/tasks/acceptance pattern
   - ✅ Make: Configurable sections

**Evaluation Gate - Week 11**:
- ✅ keepalive-runner.js evaluated function-by-function
- ✅ All helper scripts evaluated individually
- ✅ No project-specific orchestration patterns remain
- ✅ Node.js 20+ compatibility verified
- ✅ Configuration mechanism designed and documented

### Week 11-12: Workflow Integration & Cross-Repository Patterns

**Tasks**:

1. **Extract keepalive sweep job** from agents-70-orchestrator.yml:
   ```bash
   # Extract just the keepalive-related job
   # Create .github/workflows/keepalive-sweep.yml
   ```

2. **EVALUATE extracted workflow**:
   - ❌ Remove: Orchestrator-specific dependencies
   - ✅ Preserve: Sweep logic, PR discovery, keepalive execution
   - ✅ Generalize: Repository parameters, schedule configuration

3. **Copy supporting workflows**:
   ```bash
   cp .github/workflows/agents-keepalive-branch-sync.yml → .github/workflows/keepalive-branch-sync.yml
   cp .github/workflows/agents-keepalive-dispatch-handler.yml → .github/workflows/keepalive-dispatch-handler.yml
   ```

4. **EVALUATE each workflow**:
   - ❌ Remove: Agent-system specific integration
   - ✅ Preserve: Branch sync logic, dispatch handling
   - ✅ Generalize: Cross-repository reference patterns

5. **Create cross-repository integration guide**:
   - `docs/keepalive/INTEGRATION.md`:
     - How consuming repositories invoke keepalive
     - State file management patterns
     - Webhook configuration for dispatch
     - Multi-repository orchestration examples

**Evaluation Gate - Week 12**:
- ✅ All workflows evaluated individually
- ✅ Cross-repository patterns documented
- ✅ No dependencies on agent system remain
- ✅ Integration guide complete with examples

### Week 12-13: Documentation, Tests & Validation

**Tasks**:

1. **Transition keepalive documentation**:
   ```bash
   cp -r docs/keepalive/ → docs/keepalive/
   # EXCEPT: RUNTIME_STATUS.md (project-specific status tracking)
   ```

2. **EVALUATE each documentation file** (10+ files):
   - **READ each file completely**
   - Example: `docs/keepalive/GoalsAndPlumbing.md` (180 lines):
     - ✅ Preserve: Goal-plumbing pattern, guardrails, repeat contract
     - ❌ Remove: Project-specific examples
     - ✅ Generalize: Make examples parameterized
   - Create comprehensive `docs/keepalive/README.md` overview

3. **Copy and EVALUATE tests**:
   ```bash
   cp tests/workflows/test_keepalive_workflow.py → tests/workflows/test_keepalive_workflow.py
   ```
   
   - **READ test file** (~500+ lines)
   - ❌ Remove: Tests of project-specific behavior
   - ✅ Preserve: Tests of orchestration logic
   - ✅ Enhance: Add multi-repository scenario tests
   - Update harness.js fixture for keepalive runner
   - Test: `pytest tests/workflows/test_keepalive_workflow.py -v`

4. **End-to-end validation**:
   - Create test PR in Workflows repo
   - Execute keepalive sweep
   - Verify multi-round execution
   - Test branch sync
   - Test error handling
   - Validate state file management

5. **Create comprehensive guide**:
   - `docs/keepalive/GETTING_STARTED.md`:
     - Quick start guide
     - Configuration walkthrough
     - Common patterns
     - Troubleshooting

**Evaluation Gate - Week 13**:
- ✅ All documentation files evaluated individually
- ✅ Tests pass with 100% success rate
- ✅ End-to-end validation successful
- ✅ Multi-repository orchestration tested
- ✅ Getting started guide complete
- ✅ System ready for consumption

**Reference**: Complete keepalive transition in `.extraction/planning/KEEPALIVE_TRANSITION.md`

---

## Phase 6-9: Remaining Systems & Integration (Weeks 14-16)

### Phase 6: Additional Workflows (Week 14)

**Workflows**:
- PR gate template (pr-00-gate.yml → gate-template.yml)
- Tool version check (maint-50-tool-version-check.yml)
- Dependency refresh pattern (maint-51-dependency-refresh.yml)

**Process**: Apply same evaluation approach as Phase 4

### Phase 7: Supporting Actions (Week 14-15)

**Actions**:
- `.github/actions/autofix/` - Core formatting action
- `.github/actions/signature-verify/` - CI signature verification

**Process**:
- Evaluate each action's action.yml
- Evaluate supporting scripts
- Remove project-specific dependencies
- Create usage documentation

### Phase 8: Filtered Documentation Completion (Week 15)

**Complete remaining filtered documentation** from Phase 2:
- Process any deferred files from FILTER REQUIRED tier
- Finalize documentation structure
- Create comprehensive index
- Validate all cross-references

### Phase 9: Integration Testing (Week 15-16)

**Create test consumer repository**:
- New repository: `stranske/Workflows-Test-Consumer`
- Consume workflows from Workflows repository
- Test with Python project structure
- Test with Node.js project structure
- Validate all reusable workflows
- Document consumption patterns

**Evaluation Gate - Phase 9**:
- ✅ External repository successfully consumes workflows
- ✅ All reusable workflows tested end-to-end
- ✅ Documentation validated by external use
- ✅ Issues discovered and resolved

---

## Phase 10: Release & Finalization (Week 16)

### Objectives

1. **Final Documentation Review**
2. **Version Tagging**
3. **Public Release Preparation**

### Tasks

**Week 16**:

1. **Final documentation pass**:
   - Review all docs/ for completeness
   - Verify all examples are tested
   - Ensure all links functional
   - Check documentation against Phase 0 standards

2. **Create top-level documentation**:
   - `README.md`: Overview, quick start, features
   - `USAGE.md`: How to consume workflows
   - `CONFIGURATION.md`: Configuration reference
   - `EXAMPLES/`: Example projects (Python, Node.js, multi-language)
   - `CONTRIBUTING.md`: Contribution guidelines
   - `CHANGELOG.md`: Version history

3. **Version tagging**:
   ```bash
   git tag -a v1.0.0 -m "Initial public release"
   git push origin v1.0.0
   ```

4. **Create release on GitHub**:
   - Release notes highlighting features
   - Migration guide from Trend_Model_Project
   - Known limitations
   - Roadmap for v1.1

5. **Archive extraction materials**:
   ```bash
   mv .extraction/ .archive/extraction-2024-12/
   git add .archive/
   git commit -m "Archive extraction planning materials"
   ```

**Evaluation Gate - Final**:
- ✅ All documentation complete and validated
- ✅ v1.0.0 tagged and released
- ✅ Examples tested and documented
- ✅ Migration guide available
- ✅ Extraction materials archived

---

## Success Criteria

### Functional Requirements

- ✅ All core workflows executable by external repositories
- ✅ Validation system provides 2-5s, 5-30s, 30-120s tiers
- ✅ Test infrastructure validates workflow behavior
- ✅ Keepalive system supports cross-repository orchestration
- ✅ Documentation complete with working examples

### Quality Requirements

- ✅ Zero project-specific references remain
- ✅ All workflows parameterized for reusability
- ✅ Test coverage >80% for scripts
- ✅ All workflows pass actionlint validation
- ✅ Documentation evaluated for workflow appropriateness

### Process Requirements

- ✅ Every file individually evaluated (not batch copied)
- ✅ Evaluation gates passed for each phase
- ✅ Organizational patterns from audit respected
- ✅ Quality standards from Phase 0 maintained

---

## Risk Management

### High Priority Risks

1. **Mechanical Copying Without Evaluation**
   - Mitigation: Explicit evaluation steps for every file
   - Gate: Phase cannot complete without individual file evaluation

2. **Recreating Project-Specific Organizational Patterns**
   - Mitigation: Phase 0 audit identifies patterns to avoid
   - Gate: Documentation structure validated against audit baseline

3. **Incomplete Generalization**
   - Mitigation: Test with external consumer repository (Phase 9)
   - Gate: Must work in non-Trend_Model_Project context

### Medium Priority Risks

4. **Cross-Repository Keepalive Complexity**
   - Mitigation: Extensive testing in Phase 5 Week 13
   - Fallback: Document limitations for v1.0

5. **Documentation Coherence After Filtering**
   - Mitigation: Rewrite extracted content, don't just copy paragraphs
   - Gate: Read full documents for logical flow

---

## Appendices

### A. Reference Planning Documents

- `.extraction/planning/KEEPALIVE_TRANSITION.md` - 5-8 week keepalive plan
- `.extraction/planning/TEST_SEPARATION_STRATEGY.md` - 5-7 week test infrastructure plan
- `.extraction/planning/VIRTUAL_ENVIRONMENT_TRANSITION.md` - 6-week validation system plan
- `.extraction/planning/DOCS_FILTERING_MATRIX.md` - 6-week documentation filtering plan
- `.extraction/planning/WORKFLOW_INVENTORY.md` - Complete 36-workflow catalog

### B. Evaluation Checklist Template

Use for every file:

```markdown
## File Evaluation: <filename>

### 1. Read Complete
- [ ] Entire file read and understood

### 2. Evaluate Content
- [ ] Project-specific references identified
- [ ] Workflow-appropriate content identified
- [ ] Separation strategy determined

### 3. Optimize
- [ ] Project-specific content removed
- [ ] Hardcoded values parameterized
- [ ] Examples generalized

### 4. Validate
- [ ] Syntax/formatting correct
- [ ] Links functional
- [ ] Examples tested
- [ ] Coherence verified

### 5. Document
- [ ] Changes documented
- [ ] Rationale recorded
- [ ] Edge cases noted
```

### C. Timeline Summary

```
Week 1:   Phase 0 - Documentation Audit
Week 2-3: Phase 1 - Virtual Environment & Validation
Week 3-4: Phase 2 - Documentation Framework (23 + 15 files)
Week 4-6: Phase 3 - Test Infrastructure (33+ files)
Week 7-9: Phase 4 - Core Reusable Workflows
Week 10-13: Phase 5 - Keepalive System
Week 14-15: Phase 6-8 - Remaining workflows, actions, docs
Week 15-16: Phase 9 - Integration testing
Week 16: Phase 10 - Release preparation

Total: 12-16 weeks
```

---

**Plan Version**: 2.0  
**Date**: December 16, 2024  
**Author**: GitHub Copilot  
**Status**: Ready for Phase 0 execution
