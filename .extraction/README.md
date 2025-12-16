# Extraction Phase Materials

⚠️ **Temporary Directory** - This folder contains materials used only during the extraction phase when workflows are being imported from Trend_Model_Project. Once extraction is complete, this directory will be archived or removed.

## Purpose

This directory contains planning documents, tools, and resources needed to extract workflows from the source repository while ensuring quality and consistency.

## Contents

### `planning/`

Comprehensive planning documents for the extraction process:

- **TRANSITION_PLAN.md** - Master plan with 10 phases and complete strategy
- **SCRUBBING_CHECKLIST.md** - Detailed guide for removing project-specific code
- **EXTRACTION_PRIORITY.md** - Prioritized extraction matrix with time estimates
- **QUICK_REFERENCE.md** - Daily commands, templates, and patterns
- **GETTING_STARTED.md** - Step-by-step guide for contributors
- **STATUS.md** - Progress tracker and metrics
- **PLANNING_COMPLETE.md** - Planning summary and overview

**Start here**: Read `GETTING_STARTED.md` first

### `tools/`

Extraction-specific tools and utilities:

- **validate-extraction.sh** - Automated validation for extracted files

## Lifecycle

### During Extraction (Current Phase)

- Active use of all materials
- Regular updates to STATUS.md
- Tools used for validation
- Planning docs referenced daily

### After Extraction Complete

Options for this directory:

1. **Archive**: Move to `archive/extraction-YYYY-MM-DD/`
2. **Remove**: Delete after extraction is complete
3. **Preserve**: Keep select materials for future reference

**Recommendation**: Archive the planning documents for historical reference, remove temporary tools.

## Quick Links

### For Contributors

- **Getting Started**: [planning/GETTING_STARTED.md](planning/GETTING_STARTED.md)
- **What to Extract**: [planning/EXTRACTION_PRIORITY.md](planning/EXTRACTION_PRIORITY.md)
- **Daily Reference**: [planning/QUICK_REFERENCE.md](planning/QUICK_REFERENCE.md)
- **Current Status**: [planning/STATUS.md](planning/STATUS.md)

### For Understanding

- **Master Plan**: [planning/TRANSITION_PLAN.md](planning/TRANSITION_PLAN.md)
- **Complete Summary**: [planning/PLANNING_COMPLETE.md](planning/PLANNING_COMPLETE.md)

## Timeline

- **Created**: December 16, 2025
- **Expected Completion**: January-February 2026 (5-7 weeks)
- **Post-Extraction**: Archive or remove

---

**Note**: Do not use these materials for long-term repository documentation. Permanent documentation belongs in `/docs/`.
