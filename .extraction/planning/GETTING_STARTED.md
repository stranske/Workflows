# Getting Started with Workflow Extraction

Welcome! This guide will help you begin extracting workflows from Trend_Model_Project.

## What You Have

This repository contains comprehensive planning documents for extracting the workflow system:

1. **[TRANSITION_PLAN.md](TRANSITION_PLAN.md)** - Master plan with phases, structure, and strategy
2. **[SCRUBBING_CHECKLIST.md](SCRUBBING_CHECKLIST.md)** - Detailed guide for removing project-specific code
3. **[EXTRACTION_PRIORITY.md](EXTRACTION_PRIORITY.md)** - Prioritized list with time estimates
4. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick commands and templates for daily use
5. **scripts/validate-extraction.sh** - Automated validation tool

## Quick Start (15 minutes)

### 1. Review the Master Plan

Read the executive summary in [TRANSITION_PLAN.md](TRANSITION_PLAN.md) to understand:
- What workflows exist in Trend_Model_Project
- Which are reusable vs. project-specific
- The proposed repository structure
- Success criteria

### 2. Understand Priorities

Check [EXTRACTION_PRIORITY.md](EXTRACTION_PRIORITY.md) to see:
- What to extract first (Week 1: Foundation)
- Dependencies between files
- Time estimates for each file
- Risk assessment

### 3. Learn the Process

Review [QUICK_REFERENCE.md](QUICK_REFERENCE.md) for:
- Step-by-step extraction workflow
- Common find/replace patterns
- Template for adding inputs
- Validation commands

## First Extraction (Your First File)

Let's extract a simple file to get familiar with the process:

### Extract `scripts/workflow_lint.sh`

This is a great first file because:
- ✅ Low complexity (simple bash script)
- ✅ No dependencies
- ✅ Minimal scrubbing needed
- ✅ Immediate value
- ⏱️ Est. time: 1-2 hours

#### Step-by-Step:

```bash
# 1. Create scripts directory if it doesn't exist
mkdir -p scripts

# 2. Copy from Trend_Model_Project (adjust path as needed)
cp ~/Trend_Model_Project/scripts/workflow_lint.sh scripts/

# 3. Validate (should show minimal issues)
./scripts/validate-extraction.sh scripts/workflow_lint.sh

# 4. Manual review (just read through it)
cat scripts/workflow_lint.sh

# 5. Make executable
chmod +x scripts/workflow_lint.sh

# 6. Test it works
./scripts/workflow_lint.sh
# (Will show "no workflows found" but proves it runs)

# 7. Commit
git add scripts/workflow_lint.sh
git commit -m "Extract workflow_lint.sh - local actionlint runner"
```

Done! You've extracted your first file.

## Week 1 Plan (Foundation)

Follow this sequence for Week 1:

### Day 1: Simple Scripts (4-6 hours)

```bash
# Extract these in order:
1. scripts/workflow_lint.sh (1-2h) ← You just did this!
2. scripts/ci_metrics.py (2-4h)
```

### Day 2-3: More Scripts (8-12 hours)

```bash
3. scripts/ci_history.py (2-4h)
4. scripts/ci_coverage_delta.py (4-6h)
5. Create test infrastructure (2-4h)
```

### Day 4-5: Autofix Action (6-10 hours)

```bash
6. .github/actions/autofix/ (4-8h)
7. Test autofix action (2-4h)
8. Write documentation (2-3h)
```

## Tips for Success

### 1. Start Small
- Extract one file at a time
- Validate before moving to the next
- Commit frequently

### 2. Use the Tools
- Run `validate-extraction.sh` on every file
- Check the scrubbing checklist
- Reference the quick guide

### 3. Document as You Go
- Add notes to files you extract
- Update this file with lessons learned
- Keep a log of issues encountered

### 4. Test Early and Often
- Test extracted files immediately
- Create minimal test projects
- Validate in isolation

### 5. Ask for Help
- Review the detailed documentation
- Check Trend_Model_Project for context
- Document unclear decisions

## Common Pitfalls to Avoid

### ❌ Don't:
- Copy everything at once (too overwhelming)
- Skip validation (catches issues early)
- Forget to parameterize (defeats reusability purpose)
- Remove useful comments (may contain important context)
- Rush through scrubbing (quality matters)

### ✅ Do:
- Follow the priority order
- Validate each file
- Add comprehensive inputs
- Keep documentation updated
- Test with real examples
- Commit often

## Daily Workflow

### Morning (30 min)
1. Review yesterday's work
2. Check extraction priority list
3. Identify next file to extract
4. Read its documentation in Trend_Model_Project

### During Extraction (per file)
1. Copy file from source
2. Run validation script
3. Manual review for issues
4. Add parameterization
5. Test syntax/functionality
6. Create/adapt tests
7. Write documentation
8. Commit

### Evening (15 min)
1. Review day's progress
2. Update task list
3. Note any blockers
4. Plan tomorrow

## Progress Tracking

Use this section to track your progress:

### Week 1: Foundation
- [x] scripts/validate-extraction.sh (setup)
- [ ] scripts/workflow_lint.sh
- [ ] scripts/ci_metrics.py
- [ ] scripts/ci_history.py
- [ ] scripts/ci_coverage_delta.py
- [ ] .github/actions/autofix/
- [ ] Basic test infrastructure
- [ ] Initial documentation

### Week 2: Core Workflows
- [ ] reusable-10-ci-python.yml
- [ ] Tests for Python CI
- [ ] Documentation for Python CI
- [ ] First example project

### Week 3: Health & Validation
- [ ] health-42-actionlint.yml
- [ ] maint-52-validate-workflows.yml
- [ ] reusable-18-autofix.yml
- [ ] Tests and documentation

### Week 4: Additional Workflows
- [ ] reusable-12-ci-docker.yml
- [ ] health-40-sweep.yml
- [ ] maint-60-release.yml
- [ ] maint-50-tool-version-check.yml

### Week 5: Gate Template
- [ ] pr-00-gate.yml (as template)
- [ ] gate_summary.py
- [ ] detect-changes.js
- [ ] Comprehensive examples
- [ ] Complete documentation

## Success Checklist (MVP)

You'll know you're done with MVP when:

- [ ] reusable-10-ci-python.yml works in a test project
- [ ] All Week 1-3 files extracted and tested
- [ ] Basic documentation allows new user to get started
- [ ] At least 1 working example project
- [ ] All tests passing
- [ ] README reflects current state
- [ ] At least 1 external repository using the workflows

## Resources

### Documentation
- [Master Plan](TRANSITION_PLAN.md) - Overall strategy
- [Scrubbing Guide](SCRUBBING_CHECKLIST.md) - Removal patterns
- [Priority Matrix](EXTRACTION_PRIORITY.md) - What to do when
- [Quick Reference](QUICK_REFERENCE.md) - Commands and templates

### Tools
- `scripts/validate-extraction.sh` - Automated validation
- `actionlint` - Workflow linting (install: `brew install actionlint`)
- `yq` - YAML processing (install: `brew install yq`)

### Source
- [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project) - Source repository
- [Workflow System Docs](https://github.com/stranske/Trend_Model_Project/blob/main/docs/ci/WORKFLOW_SYSTEM.md) - Original documentation

## Questions?

Review the documentation first, then:

1. Check if similar file already extracted
2. Look at original in Trend_Model_Project
3. Review related documentation
4. Make a decision and document it

## Next Steps

Ready to begin? Here's what to do next:

1. ✅ Read this getting started guide (you're here!)
2. ⬜ Read the [Master Plan Executive Summary](TRANSITION_PLAN.md#executive-summary)
3. ⬜ Review [Week 1 priorities](EXTRACTION_PRIORITY.md#week-1-foundation-p0)
4. ⬜ Extract your first file (`scripts/workflow_lint.sh`)
5. ⬜ Continue with Week 1 scripts
6. ⬜ Build momentum!

---

**Good luck! Remember: slow and steady wins the race. Quality over speed.**

*Last Updated: 2024-12-16*
