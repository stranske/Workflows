# Workflows

[![Maint 62 Integration Consumer](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml/badge.svg)](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml)
[![Integration Tests](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml/badge.svg)](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml)

A reusable GitHub Actions workflow system extracted from [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project) for use across multiple repositories.

## Project Status

✅ **Extraction Complete** - Core workflow system fully extracted and validated

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✅ | Validation scripts (3 scripts, 1,018 lines) |
| Phase 2 | ✅ | Git hooks (pre-commit framework) |
| Phase 3 | ✅ | Documentation framework (17 Tier 1 docs, 6,180 lines) |
| Phase 4 | ✅ | GitHub Actions (103 files, 33,700 lines) |
| Phase 5 | ✅ | Workflow validation (actionlint verified) |
| Phase 6 | ✅ | Script testing (128/128 tests passing) |
| Phase 7 | ✅ | Infrastructure (devcontainer, 13 additional scripts) |
| Phase 8 | ✅ | Tier 2 documentation (36 additional docs) |

## What's Included

### GitHub Actions Workflows (`.github/workflows/`)

**Core CI/CD:**
- `ci-python.yaml` - Python testing, linting, type checking
- `ci-cosmetic.yaml` - Automated cosmetic repairs
- `ci-gate.yaml` - Branch protection gates

**Health & Monitoring:**
- `health-*` - Repository health checks
- `maint-*` - Maintenance workflows
- `repo-selfcheck.yaml` - Self-validation

**Agent Orchestration:**
- `agents-*.yaml` - Copilot agent automation
- `issues-*.yaml` - Issue tracking and sync

### Reusable Actions (`.github/actions/`)

- `autofix/` - Automated code formatting
- `python-setup/` - Python environment setup
- `coverage-delta/` - Coverage tracking
- `keepalive-gate/` - Keepalive validation

### Scripts

**Validation (`scripts/`):**
- `check_branch.sh` - Comprehensive branch validation
- `validate_yaml.py` - YAML syntax checking
- `sync_tool_versions.py` - Tool version management

**CI Support (`scripts/`):**
- `ci_cosmetic_repair.py` - Automated pytest repairs
- `ci_coverage_delta.py` - Coverage delta calculation
- `ledger_validate.py` - Ledger validation

### Documentation (`docs/`)

62 documentation files organized by topic:
- **CI System** - Workflows, autofix, ledger, merge queue
- **Keepalive** - Agent coordination, gap assessment
- **Guides** - User guides and reference docs
- **Archive** - Historical planning docs

## Getting Started

### Using Workflows in Your Repository

Reference workflows in your repository:

```yaml
# .github/workflows/ci.yaml
name: CI
on: [push, pull_request]

jobs:
  python-floating:
    # Floating tag for backward-compatible updates
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
    with:
      python-version: "3.11"

  python-pinned:
    # Pin to an exact release for reproducible builds
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1.0.0
    with:
      python-version: "3.11"
```

#### Versioning strategy

- **Floating major (`@v1`)** – recommended default. Receives backward-compatible fixes automatically while staying on the same major version. The floating tag is refreshed by the release pipeline and a dedicated maintenance workflow.
- **Pinned release (`@v1.0.0`)** – choose this when you need strict reproducibility and plan upgrades yourself.
- **Branch (`@main`)** – only for testing upcoming changes; may include breaking behavior.

### Local Development

1. Clone the repository
2. Open in VS Code (devcontainer recommended)
3. Install pre-commit hooks:
   ```bash
   pip install pre-commit
   pre-commit install
   ```

### Running Tests

```bash
# Run all tests
node --test .github/scripts/__tests__/*.test.js

# Run validation
./scripts/check_branch.sh
```

## Repository Structure

```
.github/
  workflows/          # 37 reusable workflows
  actions/            # 12 composite actions
  scripts/            # 49 helper scripts + tests

docs/                 # 62 documentation files
  ci/                 # CI system docs
  keepalive/          # Keepalive system docs
  guides/             # User guides
  archive/            # Historical docs

scripts/              # 19 standalone tools
  check_branch.sh     # Main validation script
  validate_yaml.py    # YAML validation

.devcontainer/        # VS Code devcontainer config
.pre-commit-config.yaml  # Pre-commit hooks
```

## Metrics

| Category | Count |
|----------|-------|
| Workflows | 37 |
| Composite Actions | 12 |
| Scripts | 68 |
| Documentation Files | 62 |
| Test Cases | 128 |
| Total Lines of Code | ~47,000 |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run validation: `./scripts/check_branch.sh`
5. Submit a pull request

Pre-commit hooks will automatically:
- Format Python with Black
- Lint with Ruff
- Validate YAML syntax
- Run fast validation checks

## License

MIT License - See [LICENSE](LICENSE) for details.

---

**Links:**
- 📚 [Documentation](docs/README.md)
- 🔧 [Workflow Guide](docs/WORKFLOW_GUIDE.md)
- 🤖 [Agent Policy](docs/AGENTS_POLICY.md)
- ⚡ [Fast Validation](docs/fast-validation-ecosystem.md)
- 🏷️ [Label Reference](docs/LABELS.md)
- 📊 [Latest Audit](docs/WORKFLOW_AUDIT_2025-12-25.md)
- 📋 [Usage Guide](docs/USAGE.md)
- 🔄 [Compatibility](docs/COMPATIBILITY.md)
- 🤝 [Contributing](docs/CONTRIBUTING.md)
