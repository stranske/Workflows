# Documentation Filtering & Transition Matrix

## Executive Summary

The Trend_Model_Project `docs/` folder contains approximately 100+ documentation files covering workflow system, CI infrastructure, development guides, and project-specific content. This matrix categorizes all documentation into three tiers: **Immediate Transition** (workflow-specific, ready to move), **Filter Required** (mixed workflow/project content), and **Exclude** (project-specific only). This structured approach ensures efficient documentation migration while maintaining clarity.

## Documentation Structure Overview

```
docs/
├── ci/                      # CI/workflow documentation (mostly IMMEDIATE)
├── keepalive/               # Keepalive system docs (IMMEDIATE)
├── workflows/               # Workflow system docs (IMMEDIATE)
├── development/             # Dev guides (FILTER)
├── ops/                     # Operations docs (FILTER)
├── debugging/               # Debug logs (FILTER/EXCLUDE)
├── archive/                 # Historical docs (FILTER/EXCLUDE)
├── directory-index/         # Folder inventories (FILTER)
└── *.md (root level)        # Various guides (FILTER)
```

## Transition Tier Definitions

### Tier 1: IMMEDIATE TRANSITION
**Criteria**: 100% workflow-specific content, no project dependencies

**Action**: Copy as-is with minimal updates (update repo references only)

**Timeline**: Week 1-2

### Tier 2: FILTER REQUIRED
**Criteria**: Mixed workflow + project content, requires content extraction

**Action**: Extract workflow-relevant sections, rewrite examples, remove project-specific references

**Timeline**: Week 3-5

### Tier 3: EXCLUDE
**Criteria**: Project-specific only, no workflow system relevance

**Action**: Do not transition

**Reference**: Document in exclusion log for future reference

---

## Documentation Inventory by Tier

### TIER 1: Immediate Transition (Workflow-Specific)

#### Category: CI & Workflow Infrastructure

| File | Size Est. | Content Summary | Action Required |
|------|-----------|-----------------|-----------------|
| `docs/ci/WORKFLOWS.md` | Medium | Workflow layout and organization, bucket system | Update repo refs |
| `docs/ci/WORKFLOW_SYSTEM.md` | Large | Complete workflow system overview, buckets, reusables | Update repo refs |
| `docs/ci/SELFTESTS.md` | Medium | Selftest workflow documentation | Update examples |
| `docs/ci/selftest_runner_plan.md` | Medium | Selftest runner architecture | Update repo refs |
| `docs/ci/pr-10-ci-python-plan.md` | Small | Python CI consolidation plan | Historical context |
| `docs/ci-workflow.md` (root) | Large | Reusable CI workflow guide, helper scripts | Update repo refs |

**Total Files**: 6  
**Estimated Effort**: 3-5 days

**Update Pattern**:
```markdown
<!-- Before -->
See `.github/workflows/pr-00-gate.yml` in Trend_Model_Project

<!-- After -->
See `.github/workflows/pr-00-gate.yml` in this repository
```

#### Category: Keepalive System

| File | Size Est. | Content Summary | Action Required |
|------|-----------|-----------------|-----------------|
| `docs/keepalive/GoalsAndPlumbing.md` | Medium | Canonical keepalive reference (~180 lines) | Copy as-is |
| `docs/keepalive/Keepalive_Reliability_Plan.md` | Medium | Failure modes and recovery | Copy as-is |
| `docs/keepalive/Observability_Contract.md` | Medium | Trace tokens, monitoring | Copy as-is |
| `docs/keepalive/Keepalive_Integration.md` | Small | Integration patterns | Copy as-is |
| `docs/keepalive/pr-*-eval-round*.md` | Variable | Evaluation examples (3-5 samples) | Select best examples |
| `docs/keepalive/status/*.md` | N/A | Runtime status (per-PR) | **EXCLUDE** (runtime data) |
| `keepalive_status.md` (root) | Small | Status index template | Document format only |

**Total Files**: ~10 (5 core + samples)  
**Estimated Effort**: 2-3 days

**Note**: Exclude all `pr-XXXX-status.md` files (runtime data). Include 2-3 evaluation examples as templates.

#### Category: Workflow System Documentation

| File | Size Est. | Content Summary | Action Required |
|------|-----------|-----------------|-----------------|
| `docs/workflows/WorkflowSystemBugReport.md` | Large | Bug analysis, API rate limiting | Update context |
| `docs/workflows/SystemEvaluation.md` | Medium | System performance evaluation | Update metrics |

**Total Files**: 2  
**Estimated Effort**: 1-2 days

#### Category: Archive (Workflow-Relevant)

| File | Size Est. | Content Summary | Action Required |
|------|-----------|-----------------|-----------------|
| `docs/archive/ARCHIVE_WORKFLOWS.md` | Large | Workflow retirement log | Copy as-is |
| `docs/archive/plans/DEPENDENCY_MANAGEMENT_SUMMARY.md` | Large | Dependency management patterns | Extract workflow sections |
| `docs/archive/plans/issues-3260-3261-keepalive-log.md` | Medium | Keepalive development log | Historical reference |
| `docs/archive/plans/actionlint-usage.md` | Medium | Actionlint integration guide | Copy as-is |
| `docs/archive/plans/validation-scripts.md` | Medium | Validation script history | Copy as-is |

**Total Files**: 5  
**Estimated Effort**: 2-3 days

**Total Tier 1**: ~23 files, 8-13 days effort

---

### TIER 2: Filter Required (Mixed Content)

#### Category: Development & Operations

| File | Size Est. | Workflow Content | Project Content | Extraction Strategy |
|------|-----------|------------------|-----------------|---------------------|
| `docs/fast-validation-ecosystem.md` | Large (300+ lines) | 80% - Validation tiers, scripts, CI integration | 20% - Project-specific examples | Extract validation system, rewrite examples |
| `docs/directory-index/scripts.md` | Large | 60% - CI scripts, validation, workflow helpers | 40% - Project scripts (analysis, demo) | Extract workflow/CI sections |
| `docs/ops/codex-bootstrap-facts.md` | Medium | 100% Codex bootstrap | Project integration examples | Generalize integration examples |
| `docs/debugging/keepalive_iteration_log.md` | Medium | Keepalive debugging patterns | Specific PR context | Extract debugging patterns, remove PR details |

**Detailed Extraction Plans**:

**1. `docs/fast-validation-ecosystem.md`**
- **Keep**: 
  - Validation tier descriptions (dev_check.sh, validate_fast.sh, check_branch.sh)
  - Tool version synchronization
  - Git hooks setup
  - IDE integration (VS Code, PyCharm)
  - CI integration patterns
  - Performance tuning
  - Troubleshooting
  
- **Remove/Replace**:
  - Examples using `src/` directory → Use `scripts/`, `.github/scripts/`
  - Streamlit app references
  - Trend analysis examples
  - Project-specific configuration paths
  
- **Effort**: 2-3 days

**2. `docs/directory-index/scripts.md`**
- **Keep**:
  - Validation scripts section
  - CI/CD scripts section
  - Automation scripts section
  - Workflow helper descriptions
  
- **Remove**:
  - Analysis & reporting scripts (run_real_model.py, benchmark_performance.py, etc.)
  - Demo generation scripts
  - Project-specific utilities
  
- **Effort**: 1 day

**3. `docs/ops/codex-bootstrap-facts.md`**
- **Keep**:
  - Codex bootstrap mechanism
  - Agent orchestration patterns
  - Workflow integration points
  
- **Generalize**:
  - Project-specific examples → Generic patterns
  - Repository references → Parameterized examples
  
- **Effort**: 1 day

**Total Files**: 4 core files  
**Estimated Effort**: 4-5 days

#### Category: Root-Level Documentation

| File | Size Est. | Workflow Relevance | Action |
|------|-----------|-------------------|--------|
| `docs/checks.md` | Small | 100% - Actionlint checks reference | Copy as-is |
| `docs/CLI.md` | Small | 0% - Trend analysis CLI | **EXCLUDE** |
| `docs/UserGuide.md` | Medium | 5% - Setup mentions validation scripts | Extract setup section only |
| `docs/install.md` | Medium | 10% - Mentions validation | Extract relevant sections |
| `docs/usage.md` | Medium | 5% - Config, testing mentions | Extract testing section |
| `docs/quickstart.md` | Small | 0% - Trend analysis quickstart | **EXCLUDE** |

**Extraction Needed**: 3 files (UserGuide, install, usage)  
**Estimated Effort**: 1-2 days

#### Category: Archive Documents (Mixed)

| File | Workflow Content | Action |
|------|------------------|--------|
| `docs/archive/plans/issue-2963-progress.md` | GitHub scripts extraction plan | Copy as-is |
| `docs/archive/README.md` | Archive index | Update for Workflows repo |
| `docs/archive/plans/*.md` (others) | Variable - need individual review | Case-by-case |

**Estimated Effort**: 2-3 days (depends on number of files reviewed)

**Total Tier 2**: ~10-15 files, 7-12 days effort

---

### TIER 3: Exclude (Project-Specific)

#### Category: Application-Specific Documentation

| File | Reason for Exclusion |
|------|---------------------|
| `docs/CLI.md` | Trend analysis CLI, not workflow-related |
| `docs/UserGuide.md` | Trend analysis user guide (except setup sections) |
| `docs/quickstart.md` | Project quickstart, no workflow content |
| `docs/INDEX.md` | Project-wide index (create new for Workflows) |
| `DOCKER_QUICKSTART.md` | Trend analysis Docker guide (not CI Docker) |
| `README_APP.md` | Streamlit app documentation |
| `CONTRIBUTING.md` | Project contribution guide (adapt for Workflows) |

#### Category: Runtime/Generated Documentation

| File/Pattern | Reason for Exclusion |
|--------------|---------------------|
| `docs/keepalive/status/PR-*.md` | Runtime status data, not system documentation |
| `keepalive_status.md` | Runtime index (document format instead) |
| `docs/debugging/*` (most files) | Specific debugging sessions, not reusable patterns |

#### Category: Archive (Project-Specific Plans)

Most files in `docs/archive/plans/` are project-specific implementation plans. Review individually, but expect 70-80% exclusion rate.

**Total Tier 3**: ~50+ files excluded

---

## Transition Process

### Phase 1: Immediate Transition (Week 1-2)

**Process**:
1. **Copy Tier 1 Files**:
   ```bash
   # Create directory structure
   mkdir -p docs/{ci,keepalive,workflows,archive}
   
   # Copy CI docs
   cp docs/ci/WORKFLOWS.md /path/to/Workflows/docs/ci/
   cp docs/ci/WORKFLOW_SYSTEM.md /path/to/Workflows/docs/ci/
   # ... (all Tier 1 files)
   
   # Copy keepalive docs
   cp -r docs/keepalive/*.md /path/to/Workflows/docs/keepalive/
   # Exclude status/ subdirectory
   ```

2. **Update Repository References**:
   ```bash
   # Find and replace repository references
   find docs/ -type f -name "*.md" -exec sed -i 's/Trend_Model_Project/Workflows/g' {} +
   find docs/ -type f -name "*.md" -exec sed -i 's|stranske/Trend_Model_Project|stranske/Workflows|g' {} +
   ```

3. **Verify Internal Links**:
   - Check all `[text](path)` links
   - Update relative paths if directory structure changed
   - Verify external links still valid

4. **Review Content**:
   - Quick scan for remaining project-specific content
   - Remove if found
   - Note if major rewrite needed (escalate to Tier 2)

**Deliverable**: 23+ docs files ready in Workflows repo

### Phase 2: Filtered Content Extraction (Week 3-5)

**Process for Each Tier 2 File**:

1. **Create Extraction Template**:
   ```markdown
   # [Document Title] - Workflow System Version
   
   > **Note**: This document has been adapted from Trend_Model_Project.
   > Project-specific content has been generalized for the Workflows repository.
   
   ## [Section 1 - Workflow Content]
   [Keep original content, update examples]
   
   ## [Section 2 - Updated Examples]
   [Replace project-specific examples with workflow examples]
   
   ---
   *Original document: docs/[path] in Trend_Model_Project*
   ```

2. **Extract Workflow Content**:
   - Copy relevant sections to new document
   - Mark sections for rewriting
   - Note removed sections in extraction log

3. **Rewrite Examples**:
   - Replace project-specific paths
   - Use workflow repository structure
   - Create generic, reusable examples

4. **Peer Review**:
   - Have second person review extraction
   - Verify no project dependencies remain
   - Confirm examples are clear

5. **Integration Testing**:
   - Follow documented procedures
   - Verify accuracy
   - Update if procedures don't work

**Example: fast-validation-ecosystem.md Extraction**:

**Original (Project-Specific)**:
```markdown
## Validation Workflow

1. Modify source code in `src/trend_analysis/`
2. Run `./scripts/dev_check.sh --changed --fix`
3. Verify Streamlit app still works
4. Run full test suite including trend analysis tests
```

**Extracted (Workflow-Generic)**:
```markdown
## Validation Workflow

1. Modify workflow scripts in `scripts/` or `.github/scripts/`
2. Run `./scripts/dev_check.sh --changed --fix`
3. Verify affected workflows execute correctly
4. Run full test suite: `pytest tests/workflows/ -v`
```

**Deliverable**: 10-15 filtered documents

### Phase 3: New Documentation Creation (Week 4-5)

**Required New Documents**:

1. **`docs/README.md`** - Workflows repository documentation index
2. **`docs/CONTRIBUTING.md`** - Contribution guide for workflow development
3. **`docs/integration/CONSUMER_GUIDE.md`** - Guide for repositories using these workflows
4. **`docs/development/SETUP.md`** - Developer environment setup
5. **`docs/development/TESTING.md`** - Testing guide for workflows

**Effort**: 3-5 days

### Phase 4: Documentation Validation (Week 5-6)

**Validation Checklist**:

**Accuracy**:
- [ ] All code examples execute successfully
- [ ] All file paths resolve correctly
- [ ] All links are valid (no 404s)
- [ ] All commands work as documented

**Completeness**:
- [ ] All workflow components documented
- [ ] All scripts have usage documentation
- [ ] All integration points explained
- [ ] Troubleshooting sections complete

**Clarity**:
- [ ] Examples are clear and self-contained
- [ ] Prerequisites listed for each guide
- [ ] Success criteria defined
- [ ] Common errors documented

**Consistency**:
- [ ] Terminology consistent across docs
- [ ] Format consistent (headings, code blocks)
- [ ] Cross-references accurate
- [ ] Navigation clear

**Testing**:
- [ ] New user can follow setup guide successfully
- [ ] Developer can run validation from docs
- [ ] Integration guide works for consumer repos
- [ ] Troubleshooting resolves common issues

**Deliverable**: Validated, production-ready documentation

---

## Detailed File-by-File Analysis

### High-Priority Immediate Transition Files

#### 1. `docs/ci/WORKFLOW_SYSTEM.md`
- **Size**: ~1,000 lines
- **Content**: Complete workflow system overview
- **Sections**:
  - Workflow buckets (PR gates, CI, agents, autofix, etc.)
  - Bucket descriptions and purposes
  - Reusable workflows
  - Helper scripts
  - Integration patterns
- **Updates Needed**:
  - Change "Trend_Model_Project" → "Workflows repository"
  - Update workflow count (may decrease after transition)
  - Remove project-specific buckets (if any)
- **Effort**: 1 day
- **Priority**: CRITICAL

#### 2. `docs/keepalive/GoalsAndPlumbing.md`
- **Size**: ~180 lines
- **Content**: Canonical keepalive reference
- **Sections**:
  - Activation guardrails
  - Repeat contract
  - Run cap enforcement
  - Pause controls
  - Trace tokens
  - Branch sync
- **Updates Needed**: Minimal (already generic)
- **Effort**: 2 hours
- **Priority**: CRITICAL

#### 3. `docs/fast-validation-ecosystem.md`
- **Size**: ~500 lines
- **Content**: Complete validation system guide
- **Sections**:
  - Validation tiers (dev_check, validate_fast, check_branch)
  - Tool version management
  - Git hooks setup
  - IDE integration (VS Code, PyCharm)
  - CI integration
  - Customization
  - Troubleshooting
- **Updates Needed**:
  - Replace project examples with workflow examples
  - Remove Streamlit/trend analysis references
  - Update file paths (src/ → scripts/)
  - Rewrite "Integration with Project" → "Integration with Consumer Repos"
- **Effort**: 2-3 days
- **Priority**: HIGH

### Medium-Priority Filter Required Files

#### 4. `docs/directory-index/scripts.md`
- **Size**: ~300 lines
- **Content**: Scripts directory inventory
- **Sections to Keep**:
  - Validation scripts (dev_check.sh, validate_fast.sh, check_branch.sh)
  - CI/CD scripts (ci_metrics.py, ci_history.py, etc.)
  - Automation scripts (keepalive-runner.js, etc.)
  - Development tools
- **Sections to Remove**:
  - Analysis & reporting (run_real_model.py, benchmark_performance.py)
  - Demo generation (generate_demo.py, run_multi_demo.py)
  - Project-specific utilities
- **Effort**: 4-6 hours
- **Priority**: MEDIUM

#### 5. `docs/ops/codex-bootstrap-facts.md`
- **Size**: ~200 lines
- **Content**: Codex bootstrap operational facts
- **Updates Needed**:
  - Generalize project examples
  - Update workflow file references
  - Add multi-repository integration patterns
- **Effort**: 3-4 hours
- **Priority**: MEDIUM

### Low-Priority Files (Extract Pattern, Not Content)

#### 6. `docs/debugging/keepalive_iteration_log.md`
- **Action**: Extract debugging methodology, discard specific PR details
- **New Document**: `docs/development/DEBUGGING_WORKFLOWS.md`
- **Content**: Generic debugging patterns
- **Effort**: 2-3 hours

---

## Documentation Quality Standards

### Required Elements for Each Document

**Header**:
```markdown
# [Document Title]

> **Audience**: [Developer | Consumer Repo Admin | CI Maintainer]  
> **Last Updated**: YYYY-MM-DD  
> **Status**: [Draft | Review | Final]
```

**Prerequisites Section**:
```markdown
## Prerequisites

- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3
```

**Quick Reference** (for long documents):
```markdown
## Quick Reference

| Task | Command |
|------|---------|
| Setup | `./scripts/setup_env.sh` |
| Validate | `./scripts/validate_fast.sh` |
```

**Examples**:
- Include working code examples
- Provide expected output
- Show both success and error cases

**Troubleshooting**:
- Common errors and solutions
- Links to detailed debugging guides
- Support contact information

**Related Documents**:
```markdown
## See Also

- [Document 1](../path/to/doc1.md)
- [Document 2](../path/to/doc2.md)
```

### Markdown Style Guide

**Headings**:
- Use ATX style (`#`, `##`, not underlines)
- One H1 per document
- Hierarchical (don't skip levels)

**Code Blocks**:
- Always specify language: ` ```python`, ` ```bash`, ` ```yaml`
- Include comments for clarity
- Show expected output when relevant

**Links**:
- Use relative paths for internal docs: `[text](../other/doc.md)`
- Use absolute URLs for external links
- Include link text that describes destination

**Lists**:
- Use `-` for unordered lists (consistent)
- Use `1.` for ordered lists (auto-numbering)
- Indent sub-items by 2 spaces

---

## Success Criteria

### Per-Phase Success Metrics

**Phase 1 (Immediate Transition) Complete**:
- [ ] 23+ Tier 1 files copied
- [ ] All repository references updated
- [ ] All internal links validated
- [ ] Quick content review completed
- [ ] No obvious project dependencies remain

**Phase 2 (Filtered Extraction) Complete**:
- [ ] 10-15 Tier 2 files extracted
- [ ] All workflow content preserved
- [ ] All examples rewritten/updated
- [ ] Peer review completed
- [ ] Integration testing passed

**Phase 3 (New Documentation) Complete**:
- [ ] README.md created
- [ ] CONTRIBUTING.md created
- [ ] Consumer guide created
- [ ] Setup guide created
- [ ] Testing guide created

**Phase 4 (Validation) Complete**:
- [ ] All code examples tested
- [ ] All links verified
- [ ] Accuracy validated
- [ ] Completeness confirmed
- [ ] Clarity verified
- [ ] Consistency checked

### Overall Documentation Quality Metrics

**Quantitative**:
- [ ] 100% of Tier 1 files transitioned
- [ ] 100% of Tier 2 files extracted or excluded
- [ ] 0 broken internal links
- [ ] 0 project-specific references in final docs
- [ ] ≥95% code example success rate

**Qualitative**:
- [ ] New developer can set up environment from docs alone
- [ ] Consumer repo can integrate workflows using guide
- [ ] All troubleshooting sections tested and accurate
- [ ] Documentation is navigable and well-organized
- [ ] Examples are clear and self-contained

---

## Timeline Summary

| Phase | Duration | Effort (Person-Days) | Critical Path |
|-------|----------|---------------------|---------------|
| Phase 1: Immediate Transition | 2 weeks | 8-13 days | Yes |
| Phase 2: Filtered Extraction | 2 weeks | 7-12 days | Yes |
| Phase 3: New Documentation | 1 week | 3-5 days | No |
| Phase 4: Validation | 1 week | 3-5 days | Yes |
| **Total** | **6 weeks** | **21-35 days** | |

**Critical Path**: Phases 1 → 2 → 4 (5 weeks minimum)

**Parallel Work**: Phase 3 (new docs) can start during Phase 2

---

## Appendix: File Transition Checklist

### Tier 1 Files (Copy & Update)

- [ ] `docs/ci/WORKFLOWS.md`
- [ ] `docs/ci/WORKFLOW_SYSTEM.md`
- [ ] `docs/ci/SELFTESTS.md`
- [ ] `docs/ci/selftest_runner_plan.md`
- [ ] `docs/ci/pr-10-ci-python-plan.md`
- [ ] `docs/ci-workflow.md`
- [ ] `docs/keepalive/GoalsAndPlumbing.md`
- [ ] `docs/keepalive/Keepalive_Reliability_Plan.md`
- [ ] `docs/keepalive/Observability_Contract.md`
- [ ] `docs/keepalive/Keepalive_Integration.md`
- [ ] `docs/keepalive/pr-*-eval-round*.md` (samples)
- [ ] `docs/workflows/WorkflowSystemBugReport.md`
- [ ] `docs/workflows/SystemEvaluation.md`
- [ ] `docs/archive/ARCHIVE_WORKFLOWS.md`
- [ ] `docs/archive/plans/actionlint-usage.md`
- [ ] `docs/archive/plans/validation-scripts.md`
- [ ] `docs/checks.md`

### Tier 2 Files (Extract & Filter)

- [ ] `docs/fast-validation-ecosystem.md`
- [ ] `docs/directory-index/scripts.md`
- [ ] `docs/ops/codex-bootstrap-facts.md`
- [ ] `docs/debugging/keepalive_iteration_log.md` (patterns only)
- [ ] `docs/UserGuide.md` (setup section only)
- [ ] `docs/install.md` (relevant sections)
- [ ] `docs/usage.md` (testing section)
- [ ] `docs/archive/plans/DEPENDENCY_MANAGEMENT_SUMMARY.md` (workflow sections)
- [ ] `docs/archive/plans/issue-2963-progress.md`

### New Documentation Required

- [ ] `docs/README.md`
- [ ] `docs/CONTRIBUTING.md`
- [ ] `docs/integration/CONSUMER_GUIDE.md`
- [ ] `docs/development/SETUP.md`
- [ ] `docs/development/TESTING.md`
- [ ] `docs/development/DEBUGGING_WORKFLOWS.md`

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX  
**Status**: Draft - Ready for Review
