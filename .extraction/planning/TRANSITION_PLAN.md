# Workflow System Extraction - Transition Plan v1.0

> **⚠️ NOTE**: This document represents the initial planning version. An updated comprehensive plan with catalytic ordering and evaluation gates has been created:
> 
> **See: [`TRANSITION_PLAN_V2.md`](TRANSITION_PLAN_V2.md)** for the current execution plan.
>
> This file is preserved for historical reference.

## Executive Summary

This plan details the extraction of the GitHub Actions workflow system from the [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project) repository into this standalone Workflows repository. The goal is to create a reusable, project-agnostic workflow system that other repositories can consume.

**Original Timeline**: 8-10 weeks  
**Updated Timeline**: See TRANSITION_PLAN_V2.md (12-16 weeks)  
**Date**: December 16, 2024  
**Status**: Superseded by v2.0 - See TRANSITION_PLAN_V2.md

---

## Update: Comprehensive Research Complete

Following initial planning, extensive research was conducted resulting in four detailed subsystem plans:

1. **Virtual Environment & Validation System** - See [VIRTUAL_ENVIRONMENT_TRANSITION.md](VIRTUAL_ENVIRONMENT_TRANSITION.md)
2. **Test Infrastructure** - See [TEST_SEPARATION_STRATEGY.md](TEST_SEPARATION_STRATEGY.md)
3. **Keepalive System** - See [KEEPALIVE_TRANSITION.md](KEEPALIVE_TRANSITION.md)
4. **Documentation Filtering** - See [DOCS_FILTERING_MATRIX.md](DOCS_FILTERING_MATRIX.md)

These findings have been integrated into **TRANSITION_PLAN_V2.md** with:
- **Catalytic phase ordering** (foundation → structure → functionality → sophistication)
- **Evaluation gates** (every file must be evaluated, not mechanically copied)
- **Preliminary documentation audit** (Phase 0 - understand before recreating)

**For execution, use TRANSITION_PLAN_V2.md**

---

## Original Plan Content (Historical Reference)

## Current State Analysis

### Workflow System Overview (from Trend_Model_Project)

The Trend_Model_Project has a sophisticated workflow system with **36 active workflow files** organized by prefixes:

- **PR Checks**: `pr-00-gate.yml`, `pr-11-ci-smoke.yml`
- **Maintenance**: `maint-45-cosmetic-repair.yml`, `maint-46-post-ci.yml`, `maint-51-dependency-refresh.yml`, `maint-52-validate-workflows.yml`, `maint-60-release.yml`, `maint-coverage-guard.yml`, `maint-47-disable-legacy-workflows.yml`, `maint-50-tool-version-check.yml`
- **Health Checks**: `health-40-repo-selfcheck.yml`, `health-40-sweep.yml`, `health-41-repo-health.yml`, `health-42-actionlint.yml`, `health-43-ci-signature-guard.yml`, `health-44-gate-branch-protection.yml`, `health-45-agents-guard.yml`, `health-50-security-scan.yml`
- **Reusable Workflows**: `reusable-10-ci-python.yml`, `reusable-12-ci-docker.yml`, `reusable-16-agents.yml`, `reusable-18-autofix.yml`, `reusable-agents-issue-bridge.yml`
- **Agents/Automation**: `agents-63-issue-intake.yml`, `agents-64-verify-agent-assignment.yml`, `agents-70-orchestrator.yml`, `agents-71-codex-belt-dispatcher.yml`, `agents-72-codex-belt-worker.yml`, `agents-73-codex-belt-conveyor.yml`, `agents-pr-meta-v4.yml`, `agents-moderate-connector.yml`, `agents-debug-issue-event.yml`, `agents-keepalive-branch-sync.yml`, `agents-keepalive-dispatch-handler.yml`
- **Autofix**: `autofix.yml`
- **Self-test**: `selftest-reusable-ci.yml`

### Supporting Infrastructure

1. **GitHub Actions** (`.github/actions/`):
   - `autofix/` - Core formatting action
   - `build-pr-comment/` - PR comment builder
   - `codex-bootstrap-lite/` - Codex PR bootstrap
   - `signature-verify/` - CI signature verification

2. **Scripts** (`.github/scripts/`):
   - `gate_summary.py` - Gate summary generation
   - `detect-changes.js` - Change detection
   - `maint-post-ci.js` - Post-CI helper
   - Others for specialized workflow tasks

3. **Python Tools** (`scripts/` and `tools/`):
   - `ci_metrics.py`, `ci_history.py`, `ci_coverage_delta.py` - CI metrics
   - `cosmetic_repair_workflow.py` - Cosmetic repair helpers
   - `workflow_lint.sh` - Local actionlint runner
   - `disable_legacy_workflows.py` - Workflow cleanup
   - Many others for dependency management, coverage tracking, etc.

4. **Tests** (`tests/workflows/`):
   - 33+ test files validating workflow behavior
   - GitHub script tests
   - Fixtures for keepalive, orchestrator, etc.

5. **Documentation** (`docs/ci/`, `docs/workflows/`, etc.):
   - `WORKFLOW_SYSTEM.md` - Comprehensive system overview
   - `WORKFLOWS.md` - Workflow catalog
   - `WORKFLOW_GUIDE.md` - Topology and routing
   - Multiple planning and operational documents

## Extraction Strategy

### Phase 1: Identify Reusable vs. Project-Specific Components

#### Highly Reusable (Priority for Extraction)

These workflows/components are generic or easily generalizable:

1. **Reusable Workflows** (all of these):
   - `reusable-10-ci-python.yml` ⭐ Core Python CI with configurable phases
   - `reusable-12-ci-docker.yml` - Docker smoke tests
   - `reusable-18-autofix.yml` - Autofix orchestration
   
2. **Health Checks**:
   - `health-42-actionlint.yml` ⭐ Workflow linting
   - `health-40-sweep.yml` - Actionlint + branch protection
   - `health-44-gate-branch-protection.yml` - Branch protection validation
   
3. **Maintenance**:
   - `maint-52-validate-workflows.yml` ⭐ Workflow validation
   - `maint-60-release.yml` - Release automation
   - `maint-50-tool-version-check.yml` - Tool version monitoring

4. **Actions**:
   - `autofix/` ⭐ Language-agnostic formatting framework
   - `signature-verify/` - CI signature verification

5. **Scripts** (generalizable):
   - `workflow_lint.sh` ⭐
   - Parts of `ci_metrics.py`, `ci_history.py`, `ci_coverage_delta.py`

#### Moderately Reusable (Require Adaptation)

These need significant generalization:

1. **PR Gate Framework**:
   - `pr-00-gate.yml` - Core gate pattern (needs template)
   - Gate summary job pattern
   - `detect-changes.js` - Generic change detection

2. **Dependency Management**:
   - `maint-51-dependency-refresh.yml` - Pattern for dependency updates
   
3. **Coverage Tracking**:
   - `maint-coverage-guard.yml` - Coverage enforcement pattern

#### Project-Specific (Not for Extraction)

These are tightly coupled to Trend_Model_Project:

1. **Agent/Codex Workflows** (entire suite):
   - `agents-70-orchestrator.yml` and all agent workflows
   - `codex-bootstrap-lite/` action
   - All keepalive infrastructure
   - Issue bridge and intake workflows

2. **Project-Specific Checks**:
   - `pr-11-ci-smoke.yml` (runs project-specific invariant tests)
   - `health-40-repo-selfcheck.yml`, `health-41-repo-health.yml` (project-specific health)
   - `maint-45-cosmetic-repair.yml` (project-specific repairs)
   - `maint-46-post-ci.yml` (project-specific post-CI)

3. **Project-Specific Actions**:
   - `build-pr-comment/` (highly project-specific)

## Phase 2: File Extraction Roadmap

### Stage 1: Core Reusable Workflows (Week 1-2)

**Files to Import:**
```
.github/workflows/reusable-10-ci-python.yml
.github/workflows/reusable-12-ci-docker.yml
.github/workflows/reusable-18-autofix.yml
.github/workflows/health-42-actionlint.yml
.github/workflows/maint-52-validate-workflows.yml
```

**Supporting Scripts:**
```
scripts/ci_metrics.py
scripts/ci_history.py
scripts/ci_coverage_delta.py
scripts/workflow_lint.sh
.github/scripts/detect-changes.js (portions)
```

**Supporting Actions:**
```
.github/actions/autofix/
```

**Tests:**
```
tests/workflows/test_reusable_ci_workflow.py
tests/workflows/test_workflow_autofix_guard.py
tests/workflows/test_workflow_naming.py (adapted)
```

**Documentation:**
```
docs/ci-workflow.md (adapted)
docs/checks.md (actionlint reference)
```

**Modifications Required:**
- Remove all references to `stranske/Trend_Model_Project`
- Parameterize repository-specific paths
- Replace hardcoded Python version pins with configurable inputs
- Remove project-specific coverage baselines
- Generalize artifact naming conventions
- Create template/example configurations

### Stage 2: Health & Validation Framework (Week 3)

**Files to Import:**
```
.github/workflows/health-40-sweep.yml
.github/workflows/health-44-gate-branch-protection.yml
.github/workflows/maint-60-release.yml
.github/workflows/maint-50-tool-version-check.yml
```

**Supporting Scripts:**
```
tools/disable_legacy_workflows.py
scripts/enforce_gate_branch_protection.py (generalized)
```

**Supporting Actions:**
```
.github/actions/signature-verify/
```

**Tests:**
```
tests/workflows/test_workflow_selftest_consolidation.py (adapted)
tests/workflows/test_disable_legacy_workflows.py
```

**Modifications Required:**
- Remove project-specific health checks
- Generalize branch protection rules (make configurable)
- Remove Trend_Model_Project-specific required status checks
- Create configuration schema for health checks
- Parameterize release workflow for different project types

### Stage 3: Gate Framework Template (Week 4)

**Files to Import (as templates):**
```
.github/workflows/pr-00-gate.yml (as gate-template.yml)
```

**Supporting Scripts:**
```
.github/scripts/gate_summary.py (generalized)
.github/scripts/detect-changes.js (completed)
```

**Tests:**
```
tests/workflows/test_workflow_naming.py
tests/workflows/github_scripts/test_gate_summary.py
```

**Documentation:**
```
docs/ci/WORKFLOW_SYSTEM.md (adapted as general guide)
docs/WORKFLOW_GUIDE.md (adapted)
```

**Modifications Required:**
- Convert to parameterized template
- Remove all Trend_Model_Project-specific job references
- Create configuration file format for gate jobs
- Document how to adapt for different project types
- Provide multiple gate examples (Python, Node.js, multi-language)

### Stage 4: Documentation & Examples (Week 5)

**New Documentation to Create:**
```
README.md - Overview and quick start
USAGE.md - How to consume workflows in your project
CONFIGURATION.md - Configuration reference
EXAMPLES/ - Example implementations for different project types
  - python-project/
  - node-project/
  - multi-language-project/
CONTRIBUTING.md - How to contribute to workflow system
CHANGELOG.md - Version history
```

**Adaptation Guide:**
```
MIGRATION.md - How to migrate from Trend_Model_Project workflows
```

## Phase 3: Generalization Checklist

### Items to Remove/Replace

1. **Repository References:**
   - ❌ All hardcoded `stranske/Trend_Model_Project` references
   - ❌ Project-specific branch names (`main`, `phase-2-dev`)
   - ❌ Project-specific path references (`tests/test_invariants.py`)
   
2. **Authentication/Secrets:**
   - ❌ `SERVICE_BOT_PAT` (project-specific)
   - ❌ Project-specific token requirements
   - ✅ Replace with generic `WORKFLOW_PAT` with clear documentation
   
3. **Python/Dependency Specifics:**
   - ❌ Hardcoded Python 3.11/3.12 versions
   - ❌ Project-specific package names (`trend_model`)
   - ❌ Hardcoded coverage minimums (75%, 72%, etc.)
   - ✅ Replace with configurable inputs/defaults
   
4. **Artifact Names:**
   - ❌ `gate-coverage`, `gate-coverage-summary`, `gate-coverage-trend`
   - ✅ Parameterize or use generic naming scheme
   
5. **Status Check Names:**
   - ❌ `Gate / gate`, `Health 45 Agents Guard`
   - ✅ Configurable status check names
   
6. **Documentation URLs:**
   - ❌ Links to Trend_Model_Project issues, PRs, runs
   - ✅ Generic placeholders or template variables

### Items to Parameterize

1. **Workflow Inputs:**
   - Repository owner/name
   - Branch names (default, development)
   - Python versions (or other language versions)
   - Coverage thresholds
   - Path patterns (docs, tests, source)
   - Required status check names
   - Artifact retention periods
   
2. **Configuration Files:**
   - Create `.github/workflows-config.yml` schema
   - Support for per-project customization
   - Validation schema for configuration
   
3. **Environment Variables:**
   - Project name
   - Language/framework type
   - CI runner preferences
   - Tool versions

## Phase 4: Testing Strategy

### Test Categories

1. **Unit Tests** (for scripts):
   - Import Python helper scripts
   - Adapt tests to remove project-specific assertions
   - Add tests for new parameterization
   
2. **Integration Tests** (for workflows):
   - Create test repository with minimal project structure
   - Test workflow invocations with different configurations
   - Validate artifact generation
   - Test error handling and edge cases
   
3. **Example Validation**:
   - Automated tests that run example configurations
   - Ensure examples work as documented
   - CI that validates examples on every change

### Test Infrastructure

```
tests/
  unit/           # Unit tests for scripts
  integration/    # Workflow integration tests
  fixtures/       # Test data
  examples/       # Example project structures for testing
```

## Phase 5: Consumption Model

### Option 1: Direct Workflow Reference (Recommended)

Consuming repositories reference workflows directly:

```yaml
name: CI
on: [push, pull_request]
jobs:
  ci:
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-versions: '["3.11", "3.12"]'
      coverage-min: '80'
```

### Option 2: Template Repository

Workflows repository serves as template:
- Users fork or use GitHub's template feature
- Customize workflows in their own `.github/workflows/`
- Benefit: Full control
- Drawback: Harder to get updates

### Option 3: Composite Actions

Convert workflows to composite actions:
- More granular reuse
- Can mix and match components
- Better for heterogeneous projects

**Recommendation**: Start with Option 1, add Option 3 for maximum flexibility.

## Phase 6: Version Management

### Versioning Strategy

1. **Semantic Versioning**: `v1.0.0`, `v1.1.0`, etc.
2. **Git Tags**: Tag major releases
3. **Branch Strategy**:
   - `main` - stable releases
   - `develop` - integration branch
   - `v1`, `v2` - major version branches for long-term support

### Breaking Changes

Document breaking changes clearly:
- Changelog entries
- Migration guides
- Deprecation warnings in workflows

### Backward Compatibility

- Maintain `v1` branch for 6-12 months after `v2` release
- Use workflow inputs with sensible defaults
- Avoid removing inputs; mark as deprecated instead

## Phase 7: Documentation Requirements

### User Documentation

1. **Quick Start Guide**:
   - 5-minute setup for common use cases
   - Copy-paste examples
   - Troubleshooting common issues
   
2. **Workflow Reference**:
   - Each workflow documented with:
     - Purpose and use cases
     - Required inputs and secrets
     - Optional inputs with defaults
     - Outputs and artifacts
     - Examples
     - Limitations
   
3. **Configuration Guide**:
   - Configuration file schema
   - All available options
   - Best practices
   
4. **Migration Guide**:
   - How to migrate from Trend_Model_Project
   - How to migrate from other CI systems
   - Common patterns and anti-patterns

### Developer Documentation

1. **Architecture Overview**:
   - How workflows interact
   - Design decisions
   - Extension points
   
2. **Contributing Guide**:
   - How to add new workflows
   - Testing requirements
   - Code review process
   
3. **Maintenance Guide**:
   - Release process
   - How to handle issues
   - Backward compatibility policy

## Phase 8: Repository Structure

### Proposed Structure

```
.github/
  workflows/          # Reusable workflows
    reusable-10-ci-python.yml
    reusable-12-ci-docker.yml
    reusable-18-autofix.yml
    health-42-actionlint.yml
    maint-52-validate-workflows.yml
    gate-template.yml
    ...
  actions/           # Composite actions
    autofix/
    signature-verify/
    ...
  scripts/          # Helper scripts for workflows
    detect-changes.js
    gate_summary.py
    ...

scripts/            # Standalone tools
  ci_metrics.py
  ci_history.py
  ci_coverage_delta.py
  workflow_lint.sh
  ...

tools/              # Utility tools
  disable_legacy_workflows.py
  ...

tests/              # Test suite
  unit/
  integration/
  fixtures/
  examples/

docs/               # Documentation
  quickstart.md
  workflows/        # Per-workflow docs
  guides/           # How-to guides
  reference/        # Reference documentation
  examples/         # Complete examples

examples/           # Example projects
  python-basic/
  python-coverage/
  node-basic/
  multi-language/

templates/          # Project templates
  .github/
    workflows/      # Starter workflows

README.md
LICENSE
CHANGELOG.md
CONTRIBUTING.md
CONFIGURATION.md
```

## Phase 9: Success Criteria

### Minimum Viable Product (MVP)

- [ ] Core Python CI workflow (`reusable-10-ci-python.yml`) extracted and working
- [ ] Actionlint workflow (`health-42-actionlint.yml`) functional
- [ ] Autofix action extracted and working
- [ ] Basic documentation (README, quickstart)
- [ ] At least one complete example
- [ ] Basic test suite passing

### Version 1.0 Goals

- [ ] All reusable workflows extracted
- [ ] All health check workflows extracted
- [ ] Gate template created and documented
- [ ] Comprehensive documentation
- [ ] Multiple examples (Python, Node.js, etc.)
- [ ] Full test coverage
- [ ] Used successfully in at least 2 repositories

### Long-term Goals

- [ ] Community adoption
- [ ] Support for multiple languages/frameworks
- [ ] Marketplace presence (if applicable)
- [ ] Integration with popular tools
- [ ] Active maintenance and support

## Phase 10: Risk Mitigation

### Risks and Mitigations

1. **Risk**: Over-coupling to Trend_Model_Project
   - **Mitigation**: Thorough review of all extracted files; extensive parameterization
   
2. **Risk**: Breaking changes in GitHub Actions
   - **Mitigation**: Version pinning; regular testing; clear upgrade paths
   
3. **Risk**: Insufficient generalization
   - **Mitigation**: Test with diverse projects early; gather feedback
   
4. **Risk**: Documentation drift
   - **Mitigation**: Auto-generate docs where possible; regular reviews; community feedback
   
5. **Risk**: Maintenance burden
   - **Mitigation**: Clear contribution guidelines; automated testing; community involvement

## Next Steps

### Immediate Actions (Week 1)

1. ✅ Create transition plan (this document)
2. [ ] Review and finalize extraction scope with stakeholders
3. [ ] Set up initial repository structure
4. [ ] Extract `reusable-10-ci-python.yml` as proof of concept
5. [ ] Create first example project
6. [ ] Set up CI for this repository

### Short-term (Weeks 2-5)

1. [ ] Complete Stage 1 extraction (core reusable workflows)
2. [ ] Implement basic test infrastructure
3. [ ] Write initial documentation
4. [ ] Create 2-3 example projects
5. [ ] Get first external consumer

### Medium-term (Months 2-3)

1. [ ] Complete all extraction stages
2. [ ] Comprehensive documentation
3. [ ] Full test coverage
4. [ ] Multiple successful consumers
5. [ ] Release v1.0

## Questions for Resolution

1. **Licensing**: What license should be used? (MIT, Apache 2.0, GPL?)
2. **Branding**: Should workflows have a distinctive name/brand?
3. **Support Model**: Issue tracker? Discussions? Community support?
4. **Release Cadence**: How often to release new versions?
5. **Compatibility**: How long to support old versions?
6. **Governance**: Solo maintainer or team? Contribution model?

## Appendix: Key Files Reference

### High-Priority Extraction List

| Priority | File | Type | Notes |
|----------|------|------|-------|
| ⭐⭐⭐ | `reusable-10-ci-python.yml` | Workflow | Core Python CI |
| ⭐⭐⭐ | `ci_metrics.py` | Script | Metrics extraction |
| ⭐⭐⭐ | `ci_history.py` | Script | History tracking |
| ⭐⭐⭐ | `ci_coverage_delta.py` | Script | Coverage delta |
| ⭐⭐⭐ | `autofix/` | Action | Core autofix |
| ⭐⭐⭐ | `docs/ci-workflow.md` | Docs | CI workflow guide |
| ⭐⭐ | `reusable-18-autofix.yml` | Workflow | Autofix orchestration |
| ⭐⭐ | `health-42-actionlint.yml` | Workflow | Workflow linting |
| ⭐⭐ | `maint-52-validate-workflows.yml` | Workflow | Workflow validation |
| ⭐⭐ | `workflow_lint.sh` | Script | Local linting |
| ⭐⭐ | `detect-changes.js` | Script | Change detection |
| ⭐⭐ | `reusable-12-ci-docker.yml` | Workflow | Docker smoke |
| ⭐ | `pr-00-gate.yml` | Workflow | Gate template |
| ⭐ | `health-40-sweep.yml` | Workflow | Health sweep |
| ⭐ | `maint-60-release.yml` | Workflow | Release automation |

### Files to Exclude (Project-Specific)

- All `agents-*` workflows (11 files)
- All keepalive infrastructure
- `codex-bootstrap-lite/` action
- `build-pr-comment/` action
- `pr-11-ci-smoke.yml`
- `health-40-repo-selfcheck.yml`
- `health-41-repo-health.yml`
- `maint-45-cosmetic-repair.yml`
- `maint-46-post-ci.yml`
- `agents-guard.yml`

---

**Document Version**: 1.0  
**Last Updated**: 2024-12-16  
**Author**: GitHub Copilot (with human review)  
**Status**: Draft - Ready for Review
