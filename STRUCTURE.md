# Repository Structure Overview

This document explains the organization of the Workflows repository and the purpose of each directory.

## Current Structure

```
Workflows/
├── .extraction/                    # ⚠️ TEMPORARY - Extraction phase materials
│   ├── README.md                   # Overview of extraction materials
│   ├── planning/                   # Planning documents
│   │   ├── TRANSITION_PLAN.md      # Master extraction plan
│   │   ├── SCRUBBING_CHECKLIST.md  # How to remove project-specific code
│   │   ├── EXTRACTION_PRIORITY.md  # Prioritized extraction matrix
│   │   ├── QUICK_REFERENCE.md      # Daily commands and templates
│   │   ├── GETTING_STARTED.md      # Contributor getting started guide
│   │   ├── STATUS.md               # Progress tracker
│   │   └── PLANNING_COMPLETE.md    # Planning summary
│   └── tools/                      # Extraction-specific tools
│       └── validate-extraction.sh  # Automated file validation
│
├── docs/                           # ✅ PERMANENT - User documentation
│   ├── README.md                   # Documentation overview
│   ├── guides/                     # How-to guides
│   │   └── README.md               # Guide catalog (to be populated)
│   ├── workflows/                  # Per-workflow documentation
│   │   └── README.md               # Workflow docs catalog (to be populated)
│   ├── examples/                   # Working examples
│   │   └── README.md               # Examples catalog (to be populated)
│   ├── reference/                  # Technical reference
│   │   └── README.md               # Reference docs catalog (to be populated)
│   └── templates/                  # Documentation templates
│       ├── README.md               # Templates overview
│       └── WORKFLOW_TEMPLATE.md    # Template for workflow docs
│
├── .github/                        # GitHub-specific configuration (to be extracted)
│   ├── workflows/                  # Reusable workflow definitions
│   │   └── [to be extracted]
│   ├── actions/                    # Composite actions
│   │   └── [to be extracted]
│   └── scripts/                    # Helper scripts for workflows
│       └── [to be extracted]
│
├── scripts/                        # Standalone tools (to be extracted)
│   └── [to be extracted]
│
├── tests/                          # Test suite (to be extracted)
│   └── [to be extracted]
│
├── .gitignore                      # Git ignore patterns
└── README.md                       # Main repository README
```

## Directory Purposes

### `.extraction/` - Temporary Extraction Materials

**Status**: Active during extraction, to be archived/removed after

This directory contains everything needed for the extraction process:

- **`planning/`**: All planning documents created before extraction started
  - Master plan, checklists, priorities, guides, status tracking
  - Used by contributors during extraction phase
  
- **`tools/`**: Extraction-specific utilities
  - Validation scripts for checking extracted files
  - Helper tools for the extraction process

**After Extraction**: Archive to `archive/extraction-2025/` or remove entirely

### `docs/` - Permanent Documentation

**Status**: Being built as extraction progresses

This is the permanent documentation that will remain after extraction:

- **`guides/`**: User-facing how-to guides and tutorials
  - Getting started guides for end users
  - Task-specific tutorials
  - Integration guides
  
- **`workflows/`**: Individual workflow documentation
  - One file per workflow
  - Complete usage documentation
  - Examples and troubleshooting
  
- **`examples/`**: Complete, runnable examples
  - Example projects by type (Python, Node.js, Docker, etc.)
  - Each example is a mini-project showing best practices
  
- **`reference/`**: Technical reference documentation
  - API documentation
  - Configuration reference
  - Troubleshooting guides
  - Changelogs and migration guides
  
- **`templates/`**: Templates for creating new documentation
  - Workflow documentation template
  - Guide template (future)
  - Example README template (future)

### `.github/` - GitHub Actions Configuration

**Status**: To be populated during extraction

Standard GitHub Actions structure:

- **`workflows/`**: Reusable workflow definitions (`.yml` files)
- **`actions/`**: Composite actions (subdirectories with `action.yml`)
- **`scripts/`**: Helper scripts called by workflows

### `scripts/` - Standalone Tools

**Status**: To be extracted

Python/Shell scripts that support the workflows but can also be used independently.

### `tests/` - Test Suite

**Status**: To be extracted

Tests for workflows, actions, and scripts to ensure quality.

## Navigation Guide

### For Contributors (During Extraction)

Start in `.extraction/`:
1. Read [.extraction/planning/GETTING_STARTED.md](.extraction/planning/GETTING_STARTED.md)
2. Check [.extraction/planning/STATUS.md](.extraction/planning/STATUS.md) for current status
3. Use [.extraction/planning/QUICK_REFERENCE.md](.extraction/planning/QUICK_REFERENCE.md) daily
4. Run [.extraction/tools/validate-extraction.sh](.extraction/tools/validate-extraction.sh) on extracted files

### For End Users (After Extraction)

Start in `docs/`:
1. Read [docs/README.md](docs/README.md) for documentation overview
2. Check [docs/guides/](docs/guides/) for how-to guides
3. Browse [docs/workflows/](docs/workflows/) for specific workflow docs
4. Try [docs/examples/](docs/examples/) to see working configurations

### For Maintainers

- Workflows: `.github/workflows/`
- Actions: `.github/actions/`
- Tests: `tests/`
- Documentation: `docs/`

## Lifecycle

### Phase 1: Planning (✅ Complete)

Created `.extraction/` with all planning materials.

### Phase 2: Extraction (Current)

- Populate `.github/workflows/`, `.github/actions/`, `scripts/`
- Create documentation in `docs/` as files are extracted
- Update `.extraction/planning/STATUS.md` regularly

### Phase 3: Post-Extraction

- Archive or remove `.extraction/`
- Finalize all documentation in `docs/`
- Establish contribution guidelines
- Release v1.0

## Key Principles

### Temporary vs. Permanent

- **Temporary**: `.extraction/` - only needed during extraction phase
- **Permanent**: Everything else - will remain in the repository

### Documentation Organization

- **User-facing**: `docs/guides/`, `docs/examples/`
- **Reference**: `docs/workflows/`, `docs/reference/`
- **Meta**: `docs/templates/`, `README.md` files

### Clean Separation

- Extraction materials don't pollute permanent structure
- Easy to remove temporary materials when done
- Clear distinction between "how we built it" and "how to use it"

## Future Structure

After extraction is complete, the structure will be:

```
Workflows/
├── .github/          # GitHub Actions (workflows, actions, scripts)
├── docs/             # Complete documentation
├── scripts/          # Standalone tools
├── tests/            # Test suite
├── examples/         # Example projects (may move to docs/examples/)
├── .gitignore
└── README.md

# .extraction/ will be archived or removed
```

---

**Last Updated**: December 16, 2025  
**See Also**: [Main README](README.md), [Documentation Overview](docs/README.md), [Extraction Overview](.extraction/README.md)
