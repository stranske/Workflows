# Extraction Priority Matrix

This document provides a prioritized list of files to extract from Trend_Model_Project, organized by complexity and dependencies.

## Priority Levels

- **P0** (Critical): Core functionality, needed by everything else
- **P1** (High): Frequently used, high value
- **P2** (Medium): Valuable but not essential for MVP
- **P3** (Low): Nice to have, can wait for v2

## Extraction Order (by week)

### Week 1: Foundation (P0)

These form the foundation and should be extracted first:

| File | Type | Complexity | Dependencies | Effort |
|------|------|------------|--------------|---------|
| `scripts/ci_metrics.py` | Script | Low | None | 2-4h |
| `scripts/ci_history.py` | Script | Low | ci_metrics.py | 2-4h |
| `scripts/ci_coverage_delta.py` | Script | Medium | ci_metrics.py | 4-6h |
| `scripts/workflow_lint.sh` | Script | Low | None | 1-2h |
| `.github/actions/autofix/` | Action | Medium | None | 4-8h |

**Total Week 1 Effort**: ~15-24 hours

**Deliverables**:
- Working CI metric scripts
- Working autofix action
- Basic test infrastructure
- Initial documentation

### Week 2: Core Workflows (P0-P1)

| File | Type | Complexity | Dependencies | Effort |
|------|------|------------|--------------|---------|
| `reusable-10-ci-python.yml` | Workflow | High | All P0 scripts | 8-12h |
| `tests/workflows/test_reusable_ci_workflow.py` | Test | Medium | reusable-10 | 4-6h |
| `docs/ci-workflow.md` | Docs | Medium | reusable-10 | 2-4h |

**Total Week 2 Effort**: ~14-22 hours

**Deliverables**:
- Working Python CI workflow
- Comprehensive tests
- Usage documentation
- First example project

### Week 3: Health & Validation (P1)

| File | Type | Complexity | Dependencies | Effort |
|------|------|------------|--------------|---------|
| `health-42-actionlint.yml` | Workflow | Medium | workflow_lint.sh | 4-6h |
| `maint-52-validate-workflows.yml` | Workflow | Medium | health-42 | 3-5h |
| `reusable-18-autofix.yml` | Workflow | Medium | autofix action | 4-6h |
| `tests/workflows/test_workflow_autofix_guard.py` | Test | Low | reusable-18 | 2-3h |
| `docs/checks.md` | Docs | Low | health-42 | 1-2h |

**Total Week 3 Effort**: ~14-22 hours

**Deliverables**:
- Workflow validation system
- Autofix orchestration
- Health check framework
- Expanded documentation

### Week 4: Additional Workflows (P1-P2)

| File | Type | Complexity | Dependencies | Effort |
|------|------|------------|--------------|---------|
| `reusable-12-ci-docker.yml` | Workflow | Medium | None | 4-6h |
| `health-40-sweep.yml` | Workflow | Medium | health-42 | 3-5h |
| `maint-60-release.yml` | Workflow | Low | None | 2-4h |
| `maint-50-tool-version-check.yml` | Workflow | Low | None | 2-3h |
| `.github/actions/signature-verify/` | Action | Low | None | 2-4h |

**Total Week 4 Effort**: ~13-22 hours

**Deliverables**:
- Docker support
- Health sweep
- Release automation
- Tool version monitoring

### Week 5: Gate Template & Polish (P2)

| File | Type | Complexity | Dependencies | Effort |
|------|------|------------|--------------|---------|
| `pr-00-gate.yml` (as template) | Template | High | Most workflows | 8-12h |
| `.github/scripts/gate_summary.py` | Script | High | ci_metrics.py | 6-10h |
| `.github/scripts/detect-changes.js` | Script | Medium | None | 4-6h |
| `tests/workflows/github_scripts/test_gate_summary.py` | Test | Medium | gate_summary.py | 3-5h |

**Total Week 5 Effort**: ~21-33 hours

**Deliverables**:
- Gate template system
- Complete examples for 3+ project types
- Comprehensive documentation
- Full test coverage

## Detailed File Analysis

### High-Value, Low-Complexity (Extract First)

These provide immediate value with minimal effort:

#### scripts/workflow_lint.sh
- **Value**: ⭐⭐⭐⭐⭐ (Essential for workflow development)
- **Complexity**: ⭐ (Simple bash script)
- **Dependencies**: None (just downloads actionlint)
- **Scrubbing needed**: Minimal
- **Time estimate**: 1-2 hours

#### maint-60-release.yml
- **Value**: ⭐⭐⭐⭐ (Standard release automation)
- **Complexity**: ⭐ (Uses standard action)
- **Dependencies**: None
- **Scrubbing needed**: Remove project-specific tag patterns
- **Time estimate**: 2-4 hours

#### .github/actions/autofix/ (core)
- **Value**: ⭐⭐⭐⭐⭐ (Widely applicable)
- **Complexity**: ⭐⭐ (Mostly tool invocations)
- **Dependencies**: None
- **Scrubbing needed**: Generalize tool detection
- **Time estimate**: 4-8 hours

### High-Value, Medium-Complexity

These are worth the effort:

#### reusable-10-ci-python.yml
- **Value**: ⭐⭐⭐⭐⭐ (Core of the system)
- **Complexity**: ⭐⭐⭐⭐ (Many moving parts)
- **Dependencies**: ci_metrics.py, ci_history.py, ci_coverage_delta.py
- **Scrubbing needed**: Extensive parameterization
- **Time estimate**: 8-12 hours
- **Why important**: This is the most valuable workflow; many projects need Python CI

#### scripts/ci_metrics.py
- **Value**: ⭐⭐⭐⭐⭐ (Used by Python CI)
- **Complexity**: ⭐⭐ (Standard Python script)
- **Dependencies**: None
- **Scrubbing needed**: Remove hardcoded paths
- **Time estimate**: 2-4 hours

#### health-42-actionlint.yml
- **Value**: ⭐⭐⭐⭐ (Essential for workflow quality)
- **Complexity**: ⭐⭐ (Wrapper around actionlint)
- **Dependencies**: workflow_lint.sh
- **Scrubbing needed**: Generalize allowlist handling
- **Time estimate**: 4-6 hours

### High-Value, High-Complexity

Save these for when foundation is solid:

#### pr-00-gate.yml (as template)
- **Value**: ⭐⭐⭐⭐⭐ (Central to CI strategy)
- **Complexity**: ⭐⭐⭐⭐⭐ (Highly project-specific)
- **Dependencies**: Almost everything
- **Scrubbing needed**: Extensive - needs to become template
- **Time estimate**: 8-12 hours
- **Why later**: Needs all other workflows working first to test properly

#### .github/scripts/gate_summary.py
- **Value**: ⭐⭐⭐⭐ (Powers gate summaries)
- **Complexity**: ⭐⭐⭐⭐ (Complex artifact handling)
- **Dependencies**: ci_metrics.py, gate workflow
- **Scrubbing needed**: Extensive parameterization
- **Time estimate**: 6-10 hours

### Medium-Value, Low-Complexity

Good for filling in gaps:

#### reusable-12-ci-docker.yml
- **Value**: ⭐⭐⭐ (Useful but not universal)
- **Complexity**: ⭐⭐ (Straightforward Docker operations)
- **Dependencies**: None
- **Scrubbing needed**: Parameterize image names
- **Time estimate**: 4-6 hours

#### maint-50-tool-version-check.yml
- **Value**: ⭐⭐⭐ (Nice monitoring)
- **Complexity**: ⭐ (Simple version checks)
- **Dependencies**: None
- **Scrubbing needed**: Generalize tool list
- **Time estimate**: 2-3 hours

## Files NOT to Extract (Project-Specific)

These should stay in Trend_Model_Project:

### Agent/Codex System (11 workflows)
- `agents-70-orchestrator.yml`
- `agents-71-codex-belt-dispatcher.yml`
- `agents-72-codex-belt-worker.yml`
- `agents-73-codex-belt-conveyor.yml`
- `agents-63-issue-intake.yml`
- `agents-64-verify-agent-assignment.yml`
- `agents-pr-meta-v4.yml`
- `agents-moderate-connector.yml`
- `agents-debug-issue-event.yml`
- `agents-keepalive-branch-sync.yml`
- `agents-keepalive-dispatch-handler.yml`

**Reason**: Highly specific to Trend_Model_Project's Codex automation system

### Project-Specific Health Checks
- `health-40-repo-selfcheck.yml`
- `health-41-repo-health.yml`
- `health-45-agents-guard.yml`

**Reason**: Check project-specific conditions

### Project-Specific Maintenance
- `maint-45-cosmetic-repair.yml`
- `maint-46-post-ci.yml`

**Reason**: Project-specific cleanup and post-CI operations

### Project-Specific CI
- `pr-11-ci-smoke.yml`

**Reason**: Runs project-specific invariant tests

## Dependency Graph

```
Legend: A → B means "A depends on B"

reusable-10-ci-python.yml → ci_metrics.py
                          → ci_history.py
                          → ci_coverage_delta.py
                          
reusable-18-autofix.yml → autofix/ action

health-42-actionlint.yml → workflow_lint.sh

health-40-sweep.yml → health-42-actionlint.yml
                    → health-44-gate-branch-protection.yml

maint-52-validate-workflows.yml → workflow_lint.sh

pr-00-gate.yml (template) → reusable-10-ci-python.yml
                          → reusable-12-ci-docker.yml
                          → detect-changes.js
                          → gate_summary.py

gate_summary.py → ci_metrics.py
```

## Extraction Phases Summary

### MVP (Weeks 1-3) - Total ~43-68 hours

**Files Extracted**: ~15 files
- All P0 scripts
- Core reusable workflows (Python CI, Autofix)
- Basic health checks
- Essential tests and docs

**Capability**: 
- ✅ Python projects can use reusable CI
- ✅ Workflows can be validated
- ✅ Autofix can be applied
- ✅ Basic examples work

### V1.0 (Weeks 1-5) - Total ~77-119 hours

**Files Extracted**: ~25-30 files
- Everything from MVP
- Docker support
- Gate template
- Comprehensive health checks
- Complete documentation

**Capability**:
- ✅ Multi-language projects supported
- ✅ Full gate system available
- ✅ Comprehensive health monitoring
- ✅ Production-ready for diverse projects

### V2.0 (Future) - Additional features

**Potential Additions**:
- Node.js specific workflows
- Go specific workflows
- More health checks
- More maintenance automations
- Additional autofix tools

## Critical Path

The critical path for getting to MVP is:

1. **ci_metrics.py** (2-4h) → Needed by Python CI
2. **ci_history.py** (2-4h) → Needed by Python CI  
3. **ci_coverage_delta.py** (4-6h) → Needed by Python CI
4. **reusable-10-ci-python.yml** (8-12h) → Core workflow
5. **Test + Document** (6-10h) → Validation

**Critical Path Total**: 22-36 hours

Everything else can be parallelized or done after the critical path.

## Risk Assessment

### High Risk (Needs Careful Attention)

| File | Risk | Mitigation |
|------|------|------------|
| `reusable-10-ci-python.yml` | Complex dependencies | Extract helpers first; extensive testing |
| `pr-00-gate.yml` | Highly project-specific | Create as template; provide multiple examples |
| `gate_summary.py` | Complex artifact handling | Comprehensive parameterization; clear docs |

### Medium Risk

| File | Risk | Mitigation |
|------|------|------------|
| `reusable-18-autofix.yml` | Tool detection logic | Make configurable; support multiple tools |
| `ci_coverage_delta.py` | Coverage calculation edge cases | Extensive testing with various inputs |

### Low Risk

Most other files are low risk - straightforward extraction with minimal dependencies.

## Testing Strategy by Phase

### Week 1-2 (Foundation)
- Unit tests for Python scripts
- Basic workflow syntax validation
- Test with minimal example project

### Week 3-4 (Expansion)
- Integration tests for workflow interactions
- Test with 2-3 different project types
- Validate all configuration options

### Week 5 (Polish)
- End-to-end tests for complete workflows
- Test all example projects
- Performance testing
- Documentation review

## Success Metrics

### MVP Success (End of Week 3)
- [ ] reusable-10-ci-python.yml works in 2+ projects
- [ ] All tests passing
- [ ] Documentation allows new user to get started in <30 min
- [ ] At least 1 external consumer (beyond Trend_Model_Project)

### V1.0 Success (End of Week 5)
- [ ] All P0-P1 workflows extracted and tested
- [ ] 3+ example projects working
- [ ] Comprehensive documentation
- [ ] 3+ external consumers
- [ ] Positive feedback from users

---

**Document Version**: 1.0  
**Last Updated**: 2024-12-16  
**Status**: Ready for Use

**Usage**: Reference this matrix when planning extraction work. Update as priorities shift or new dependencies are discovered.
