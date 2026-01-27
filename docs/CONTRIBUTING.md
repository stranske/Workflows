# Contributing to Workflows

Thank you for your interest in contributing!

## Development Setup

### Prerequisites

- Node.js 20+
- Python 3.11+
- Git

### Local Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/stranske/Workflows.git
   cd Workflows
   ```

2. Set up Python environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install pre-commit black ruff mypy pytest
   ```

3. Install pre-commit hooks:
   ```bash
   pre-commit install --hook-type pre-commit --hook-type pre-push
   ```

### Using the Devcontainer

For the easiest setup, open this repository in VS Code with the Remote Containers extension. The devcontainer includes all dependencies pre-configured.

## Running Tests

### JavaScript Tests (128 tests)

```bash
node --test .github/scripts/__tests__/*.test.js
```

### Python Tests (188 tests)

```bash
source .venv/bin/activate
python -m pytest tests/workflows/ -v
```

### All Tests

```bash
# JS tests
node --test .github/scripts/__tests__/*.test.js

# Python tests (excluding project-specific)
python -m pytest tests/workflows/ \
  --ignore-glob='**/test_autofix*.py' \
  --ignore-glob='**/test_workflow_multi*.py' \
  --ignore-glob='**/test_disable*.py' \
  --ignore-glob='**/test_chatgpt*.py' \
  --ignore-glob='**/test_ci_probe*.py' \
  --ignore-glob='**/github_scripts/*'
```

## Validation

Before submitting changes, run the validation scripts:

```bash
# Quick check (2-5 seconds)
./scripts/dev_check.sh

# Comprehensive check (30-120 seconds)
./scripts/check_branch.sh

# Template sync validation (if you modified .github/scripts/)
python scripts/validate_template_sync.py
```

### ⚠️ CRITICAL: Template Sync Guard

**If you modify any file in `.github/scripts/`, you MUST also update the template:**

```bash
# After editing .github/scripts/*.js, run:
./scripts/sync_templates.sh

# Verify sync:
python scripts/validate_template_sync.py
```

**Why?** Consumer repos get workflow updates via `templates/consumer-repo/`. If you only update `.github/scripts/` but not the template, your changes won't sync to consumer repos and no sync PRs will be created.

The CI will fail if templates are out of sync with source files.

## Code Style

### Python

- **Formatter**: Black (line length 88)
- **Linter**: Ruff
- **Type Checker**: Mypy

Pre-commit hooks automatically format and lint Python code.

### JavaScript

- Use modern ES6+ syntax
- Follow existing code patterns
- Include tests for new functionality
- **Wrap all GitHub API calls with token-aware retry** - See [API_CALL_PATTERN.md](../.github/scripts/API_CALL_PATTERN.md)

### YAML

- 2-space indentation
- Use `workflow_call` for reusable workflows
- Document all inputs and outputs

## Making Changes

### Workflows

1. Create/modify workflow in `.github/workflows/`
2. Add corresponding tests if applicable
3. Update documentation in `docs/workflows/`
4. Run validation

### Actions

1. Create/modify action in `.github/actions/<action-name>/`
2. Include `action.yml` with documented inputs/outputs
3. Add tests
4. Update USAGE.md if adding new action

### Scripts

1. Add script to appropriate location:
   - `.github/scripts/` - Workflow helper scripts
   - `scripts/` - Standalone tools
2. Include tests in `__tests__/` or `tests/workflows/`
3. Make executable if has shebang: `chmod +x script.sh`
4. **Wrap all GitHub API calls** - See [API_CALL_PATTERN.md](../.github/scripts/API_CALL_PATTERN.md)
5. Run the API guard: `node .github/scripts/__checks__/api-call-guard.js`

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run all tests and validation
5. Commit with descriptive message
6. Push and create Pull Request

### PR Checklist

- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Pre-commit hooks pass
- [ ] Validation scripts pass
- [ ] No old repo references
- [ ] GitHub API calls use token-aware retry (run `node .github/scripts/__checks__/api-call-guard.js`)

## Questions?

- Check existing [documentation](docs/)
- Open an issue for bugs or feature requests
- See [WORKFLOW_GUIDE.md](docs/WORKFLOW_GUIDE.md) for workflow architecture
