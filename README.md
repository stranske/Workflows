# Workflows

A reusable GitHub Actions workflow system extracted from [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project) for use across multiple repositories.

## Project Status

🚧 **Phase 0: Planning Complete** - Ready to begin extraction

See [STATUS.md](STATUS.md) for detailed progress tracking.

## Overview

This repository will provide a comprehensive set of reusable GitHub Actions workflows, composite actions, and supporting scripts that can be consumed by other repositories. The workflows will support:

- **Python CI/CD** - Testing, linting, type checking, and coverage tracking
- **Docker** - Container builds and smoke tests  
- **Autofix** - Automated code formatting and cleanup
- **Health Checks** - Repository health monitoring and validation
- **Workflow Linting** - Actionlint integration for workflow validation
- **Release Automation** - Automated release management

## Documentation

### For Project Contributors (Extraction Phase)

Start here if you're helping with the extraction:

- 📖 **[Getting Started Guide](.extraction/planning/GETTING_STARTED.md)** - Start here! Step-by-step guide to begin extraction
- 📊 **[Project Status](.extraction/planning/STATUS.md)** - Current progress and metrics
- 🗓️ **[Extraction Priority Matrix](.extraction/planning/EXTRACTION_PRIORITY.md)** - What to extract when, with time estimates
- ⚡ **[Quick Reference](.extraction/planning/QUICK_REFERENCE.md)** - Commands, templates, and patterns for daily use

**Full extraction documentation**: [.extraction/README.md](.extraction/README.md)

### Planning Documents (Temporary)

Comprehensive planning for the extraction process (in `.extraction/planning/`):

- 📋 **[Master Transition Plan](.extraction/planning/TRANSITION_PLAN.md)** - Overall strategy, phases, and structure
- 🧹 **[Scrubbing Checklist](.extraction/planning/SCRUBBING_CHECKLIST.md)** - How to remove project-specific elements
- 🛠️ **[Validation Script](.extraction/tools/validate-extraction.sh)** - Automated file validation

### For End Users (Permanent)

_(Being built in `docs/` as workflows are extracted)_

- **[Documentation Overview](docs/README.md)** - Main documentation hub
- **[User Guides](docs/guides/)** - How-to guides and tutorials
- **[Workflow Docs](docs/workflows/)** - Individual workflow documentation
- **[Examples](docs/examples/)** - Working examples by project type
- **[Reference](docs/reference/)** - Technical reference documentation

## Getting Started

### As a Contributor (Extracting Workflows)

1. Read the [Getting Started Guide](.extraction/planning/GETTING_STARTED.md)
2. Review [Week 1 priorities](.extraction/planning/EXTRACTION_PRIORITY.md#week-1-foundation-p0)
3. Extract your first file following the [Quick Reference](.extraction/planning/QUICK_REFERENCE.md)
4. Update [STATUS.md](.extraction/planning/STATUS.md) as you progress

### As a User (Using Workflows)

Coming soon after MVP extraction is complete.

## Repository Structure

```
.github/
  workflows/          # Reusable workflows (to be extracted)
  actions/            # Composite actions (to be extracted)
  scripts/            # Helper scripts for workflows (to be extracted)

docs/                 # Permanent documentation
  guides/             # User guides and tutorials
  workflows/          # Individual workflow documentation
  examples/           # Example configurations
  reference/          # Technical reference
  templates/          # Documentation templates

.extraction/          # Temporary extraction materials
  planning/           # Planning documents
  tools/              # Extraction-specific tools

scripts/              # Standalone tools (to be extracted)
tests/                # Test suite (to be extracted)

README.md             # This file
```

**Detailed structure**: See [STRUCTURE.md](STRUCTURE.md) for complete directory organization

## Extraction Timeline

- **Week 1** (Dec 16-23): Foundation scripts and autofix action
- **Week 2** (Dec 23-30): Core Python CI workflow
- **Week 3** (Dec 30-Jan 6): Health checks and validation
- **Week 4** (Jan 6-13): Additional workflows
- **Week 5** (Jan 13-20): Gate template and examples
- **Jan 20, 2025**: 🚀 MVP Release (v0.1.0)

See [STATUS.md](.extraction/planning/STATUS.md) for detailed timeline and current progress.

## Contributing

This repository is currently in the extraction phase. If you'd like to help:

1. Check [STATUS.md](.extraction/planning/STATUS.md) for what needs to be done
2. Follow the [Getting Started Guide](.extraction/planning/GETTING_STARTED.md)
3. Use the provided tools and checklists (in `.extraction/`)
4. Update status as you make progress

Contribution guidelines will be formalized once the initial workflow system is operational.

## License

_(To be determined)_

---

**Quick Links**:
- 🎯 [What to do next?](.extraction/planning/GETTING_STARTED.md#next-steps)
- 📊 [Current status](.extraction/planning/STATUS.md#current-phase)
- ⏱️ [Time estimates](.extraction/planning/EXTRACTION_PRIORITY.md#extraction-order-by-week)
- 🔍 [Validation tool](.extraction/tools/validate-extraction.sh)
- 📚 [Documentation hub](docs/README.md)
