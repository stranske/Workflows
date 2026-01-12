# Workflows

[![Maint 62 Integration Consumer](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml/badge.svg)](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml)
[![Integration Tests](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml/badge.svg)](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml)

A reusable GitHub Actions workflow system for Python projects with integrated agent automation (Codex keepalive, autofix, CI orchestration).

## Project Status

✅ **Production Ready** - Actively used and maintained.

### First-party Consumers

- Travel-Plan-Permission
- Template
- trip-planner
- Manager-Database
- Portable-Alpha-Extension-Model

## What's Included

### Reusable Workflows (.github/workflows)

- CI: `reusable-10-ci-python.yml`, `reusable-11-ci-node.yml`, `reusable-12-ci-docker.yml`
- Agent automation: `reusable-16-agents.yml`, `reusable-codex-run.yml`, `reusable-20-pr-meta.yml`
- Orchestration: `reusable-70-orchestrator-init.yml`, `reusable-70-orchestrator-main.yml`

### First-party Orchestration Workflows (.github/workflows)

- Gate: `pr-00-gate.yml` (single PR-required check)
- Maintenance & health: `maint-*`, `health-*`
- Agents: `agents-*`

### Composite Actions (.github/actions)

- `autofix/` - Formatting and hygiene automation
- `python-ci-setup/` - Python environment setup for CI
- `signature-verify/` - Signature/manifest verification helpers
- `codex-bootstrap-lite/` - Lightweight bootstrap utilities for agent runs

### Scripts

**Validation (`scripts/`):**
- `check_branch.sh` - Comprehensive branch validation
- `validate_yaml.py` - YAML syntax checking
- `sync_tool_versions.py` - Tool version management

**CI Support (`scripts/`):**
- `ci_cosmetic_repair.py` - Automated pytest repairs
- `ci_coverage_delta.py` - Coverage delta calculation
- `ledger_validate.py` - Ledger validation

### Issue Intake Task Decomposition

The GitHub issue creation workflow (`agents-63-issue-intake.yml`) formats newly
created issues by running `scripts/langchain/issue_formatter.py`. The formatter
now integrates `scripts/langchain/task_decomposer.py` to split multi-action
Tasks into smaller, verifiable sub-tasks and inserts them under each original
task in the formatted issue body.

### Documentation (docs)

Start with:
- `docs/USAGE.md`
- `docs/INTEGRATION_GUIDE.md`
- `docs/ci-workflow.md`
- `docs/keepalive/SETUP_CHECKLIST.md`

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
# Fast local validation (syntax, workflows, lint, typecheck, keepalive JS tests)
./scripts/dev_check.sh

# Comprehensive validation
./scripts/check_branch.sh
```

## Repository Structure

```
.github/
  workflows/          # Workflows (reusable + first-party orchestration)
  actions/            # Composite actions
  scripts/            # JS helpers used by workflows (includes tests)

docs/                 # Documentation
scripts/              # Standalone tooling and validation scripts
templates/            # Consumer templates and examples
tests/                # Python tests
```

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
- Documentation: docs/README.md
- Usage: docs/USAGE.md
- Integration guide: docs/INTEGRATION_GUIDE.md
- CI wiring: docs/ci-workflow.md
- Keepalive setup: docs/keepalive/SETUP_CHECKLIST.md
- Workflow guide: docs/WORKFLOW_GUIDE.md
- Agent policy: docs/AGENTS_POLICY.md
- Compatibility: docs/COMPATIBILITY.md
- Contributing: docs/CONTRIBUTING.md
