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

## Auto-Pilot Pipeline

The `agents:auto-pilot` label triggers a fully automated issue-to-merge pipeline.
This is the primary automation system for both the Workflows repo and all consumer repos.

```
Issue created ──▶ Format ──▶ Optimize ──▶ Apply ──▶ Capability Check
                                                         │
                                                         ▼
                          ◀── Verify ◀── Merge ◀── Keepalive ◀── Create PR
                          │
                    ┌─────┴──────┐
                    │ PASS       │ CONCERNS/FAIL
                    ▼            ▼
                  Done     Follow-up Issue (capped at depth 2)
```

### Pipeline Stages

| Stage | What Happens |
|-------|-------------|
| **Format** | `issue_formatter.py` + `task_decomposer.py` restructure the issue into Why / Scope / Tasks / Acceptance Criteria |
| **Optimize** | `issue_optimizer.py` analyzes the repo codebase and adds file paths, patterns, and conflict warnings |
| **Apply** | Enriches issue tasks with optimizer suggestions |
| **Capability Check** | Validates issue suitability for automation; assigns `agent:codex` label |
| **Create PR** | Creates `codex/issue-*` branch with issue context in PR body |
| **Keepalive** | Event-driven loop (Gate completion → task appendix → Codex CLI dispatch → push → repeat) |
| **Verify** | LLM-based evaluation of PR against acceptance criteria (PASS / CONCERNS / FAIL) |
| **Follow-up** | On CONCERNS/FAIL, creates a follow-up issue with verification gaps as tasks (target max depth 2; automated enforcement pending) |

### Self-Dispatch Mechanism

Auto-pilot uses `workflow_dispatch` with a `force_step` input to chain stages sequentially.
This eliminates label-trigger race conditions that plagued earlier designs.
Each stage completes, then dispatches auto-pilot again with the next step name.

### Key Design Decisions

- **Event-driven keepalive** — Gate `workflow_run` completion triggers iteration, not polling
- **Task appendix injection** — Agent prompts include explicit, structured task context from the issue
- **Token-aware retry** — `withRetry` + `token_load_balancer.js` distributes API calls across PATs and GitHub App tokens
- **Verification pipeline** — Dual-model `verify:compare` catches quality gaps post-merge; see metrics below

### Verification Pipeline

After PR merge, applying a `verify:*` label (typically `verify:evaluate` via auto-pilot, or `verify:compare` for dual-model mode) triggers the verifier. In `compare` mode, two LLM providers (gpt-5.2 + claude-sonnet-4-5) independently evaluate the diff against acceptance criteria with unanimous PASS required. On CONCERNS or FAIL, maintainers or automation can apply the `verify:create-new-pr` label to trigger a 4-round LLM pipeline that generates a follow-up issue (analyze → tasks → acceptance criteria → format).

**Current Metrics (Feb 2026, 40-PR sample across Workflows + Trend_Model_Project):**

| Metric | Value | Target |
|--------|------:|-------:|
| First-fix rate | 35% | 60% |
| Average chain depth | 2.7 | 1.5 |
| Max chain depth | 6 | 3 |
| Verifier signal quality | 75% | 85% |
| needs-human rate | 40% | 30% |

For the full evaluation and recommendations, see [`docs/analysis/verify-compare-40pr-evaluation-feb-2026.md`](docs/analysis/verify-compare-40pr-evaluation-feb-2026.md).

---

## What's Included

### Reusable Workflows (.github/workflows)

- CI: `reusable-10-ci-python.yml`, `reusable-11-ci-node.yml`, `reusable-12-ci-docker.yml`
- Agent automation: `reusable-16-agents.yml`, `reusable-codex-run.yml`, `reusable-20-pr-meta.yml`
- Orchestration: `reusable-70-orchestrator-init.yml`, `reusable-70-orchestrator-main.yml`

### First-party Orchestration Workflows (.github/workflows)

- Gate: `pr-00-gate.yml` (single PR-required check)
- Maintenance & health: `maint-*`, `health-*`
- Agents: `agents-*` (auto-pilot, verifier, keepalive, issue-intake, pr-meta)

### Composite Actions (.github/actions)

- `autofix/` - Formatting and hygiene automation
- `python-ci-setup/` - Python environment setup for CI
- `signature-verify/` - Signature/manifest verification helpers
- `codex-bootstrap-lite/` - Lightweight bootstrap utilities for agent runs
- `setup-api-client/` - Token export and API client initialization

### Scripts

**Validation (`scripts/`):**
- `check_branch.sh` - Comprehensive branch validation
- `validate_yaml.py` - YAML syntax checking
- `sync_tool_versions.py` - Tool version management

**CI Support (`scripts/`):**
- `ci_cosmetic_repair.py` - Automated pytest repairs
- `ci_coverage_delta.py` - Coverage delta calculation
- `ledger_validate.py` - Ledger validation

**Agent Pipeline (`scripts/langchain/`):**
- `issue_formatter.py` - Issue restructuring for agent consumption
- `task_decomposer.py` - Multi-action task splitting
- `issue_optimizer.py` - Repo-aware issue enrichment

**Rate Limiting (`.github/scripts/`):**
- `github-api-with-retry.js` - Exponential backoff + token rotation
- `token_load_balancer.js` - Multi-token registry and optimal selection

### Documentation (docs)

Start with:
- `docs/USAGE.md`
- `docs/INTEGRATION_GUIDE.md`
- `docs/ci-workflow.md`
- `docs/keepalive/SETUP_CHECKLIST.md`
- `docs/analysis/verify-compare-40pr-evaluation-feb-2026.md` - Verify:compare pipeline evaluation (Feb 2026)

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
