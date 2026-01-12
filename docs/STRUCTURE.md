# Repository Structure

```
Workflows/
├── .github/                        # GitHub Actions system
│   ├── workflows/                  # 37 reusable workflows
│   │   ├── ci-*.yaml               # CI/CD workflows
│   │   ├── health-*.yaml           # Health check workflows
│   │   ├── maint-*.yaml            # Maintenance workflows
│   │   ├── agents-*.yaml           # Agent orchestration
│   │   └── issues-*.yaml           # Issue management
│   ├── actions/                    # 12 composite actions
│   │   ├── autofix/                # Automated formatting + lint fixes
│   │   ├── python-ci-setup/        # Python environment + dependency install
│   │   ├── build-pr-comment/       # PR comment builder helpers
│   │   └── signature-verify/       # CI signature verification
│   └── scripts/                    # 49 workflow helper scripts
│       ├── __tests__/              # 128 test cases
│       └── *.js                    # JavaScript helpers
│
├── scripts/                        # 19 standalone tools
│   ├── check_branch.sh             # Main validation script
│   ├── validate_yaml.py            # YAML validation
│   ├── dev_check.sh                # Pre-commit validation
│   ├── validate_fast.sh            # Pre-push validation
│   └── ci_*.py                     # CI helper scripts
│
├── docs/                           # 62 documentation files
│   ├── README.md                   # Documentation hub
│   ├── ci/                         # CI system documentation
│   │   ├── WORKFLOWS.md            # Workflow reference
│   │   ├── AUTOFIX.md              # Autofix system
│   │   ├── LEDGER.md               # Ledger system
│   │   └── MERGE_QUEUE.md          # Merge queue config
│   ├── keepalive/                  # Keepalive system
│   │   ├── GoalsAndPlumbing.md     # System overview
│   │   └── Observability_Contract.md
│   ├── guides/                     # User guides
│   ├── reference/                  # Technical reference
│   ├── templates/                  # Doc templates
│   ├── archive/                    # Historical docs
│   │   └── plans/                  # Planning archives
│   └── ops/                        # Operations docs
│
├── .devcontainer/                  # VS Code devcontainer
│   └── devcontainer.json           # Container config
│
├── .extraction/                    # Extraction tracking (internal)
│   ├── planning/                   # Original planning docs
│   ├── phases/                     # Phase completion records
│   └── evaluations/                # Evaluation docs
│
├── README.md                       # Repository overview
├── .pre-commit-config.yaml         # Pre-commit hooks
├── .gitignore                      # Git ignore rules
└── pyproject.toml                  # Python config (ruff, black)
```

## Key Directories

### `.github/workflows/`
Reusable GitHub Actions workflows. Reference from other repos:
```yaml
uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@v1
```

### `.github/actions/`
Composite actions for common tasks. Use in workflow steps:
```yaml
- uses: stranske/Workflows/.github/actions/autofix@v1
```

### `scripts/`
Standalone validation and utility scripts. Run locally:
```bash
./scripts/check_branch.sh
```

### `docs/`
All user-facing documentation organized by topic.
