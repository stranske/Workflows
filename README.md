# Workflows

[![Maint 62 Integration Consumer](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml/badge.svg)](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml)
[![Integration Tests](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml/badge.svg)](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml)

A reusable GitHub Actions workflow system for Python projects with integrated agent automation (Codex keepalive, autofix, CI orchestration).

For a narrative of how the repo evolved through five development phases (bootstrap → v1.1.x → Feb consolidation → production quiet → re-engagement) and where it stands today, see [`docs/HISTORY.md`](docs/HISTORY.md).

## Project Status

✅ **Production Ready** - Actively used and maintained.

### First-party Consumers

13 repos are currently registered as first-party consumers (synced via [`.github/workflows/maint-68-sync-consumer-repos.yml`](.github/workflows/maint-68-sync-consumer-repos.yml)):

- [Travel-Plan-Permission](https://github.com/stranske/Travel-Plan-Permission)
- [Template](https://github.com/stranske/Template)
- [trip-planner](https://github.com/stranske/trip-planner)
- [Manager-Database](https://github.com/stranske/Manager-Database)
- [Portable-Alpha-Extension-Model](https://github.com/stranske/Portable-Alpha-Extension-Model)
- [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project)
- [Collab-Admin](https://github.com/stranske/Collab-Admin)
- [Counter_Risk](https://github.com/stranske/Counter_Risk)
- [Pension-Data](https://github.com/stranske/Pension-Data)
- [Inv-Man-Intake](https://github.com/stranske/Inv-Man-Intake)
- [Ready](https://github.com/stranske/Ready)
- [learning-management-system](https://github.com/stranske/learning-management-system)
- [Fine-Art-Archive](https://github.com/stranske/Fine-Art-Archive)

[`.github/workflows/maint-68-sync-consumer-repos.yml`](.github/workflows/maint-68-sync-consumer-repos.yml) is the authoritative list — `REGISTERED_CONSUMER_REPOS` env var. The [Workflows-Integration-Tests](https://github.com/stranske/Workflows-Integration-Tests) harness validates the consumer surface separately.

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

After PR merge, applying a `verify:*` label (typically `verify:evaluate` via auto-pilot, or `verify:compare` for dual-model mode) triggers the verifier. In `compare` mode, two LLM providers (gpt-5.4 + claude-sonnet-4-6) independently evaluate the diff against acceptance criteria with unanimous PASS required. On CONCERNS or FAIL, maintainers or automation can apply the `verify:create-new-pr` label to trigger a 4-round LLM pipeline that generates a follow-up issue (analyze -> tasks -> acceptance criteria -> format).

**Live verifier and pipeline metrics** are surfaced through the weekly summary tracker — see [issue #1796](https://github.com/stranske/Workflows/issues/1796) (durable auto-bot tracker, posted Mondays at 06:00 UTC) and the LangSmith dashboard wired by [`maint-80-langsmith-metrics-dashboard.yml`](.github/workflows/maint-80-langsmith-metrics-dashboard.yml). The original Feb 2026 baseline (40-PR sample, first-fix 35%, avg chain depth 2.7) is preserved at [`docs/analysis/verify-compare-40pr-evaluation-feb-2026.md`](docs/analysis/verify-compare-40pr-evaluation-feb-2026.md) for historical comparison.

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
- `templates/consumer-repo/docs/SETUP_CHECKLIST.md`
- `docs/guides/ADD_NEW_AGENT.md` — Checklist for onboarding new automation agents
- `docs/analysis/verify-compare-40pr-evaluation-feb-2026.md` - Verify:compare pipeline evaluation (Feb 2026)

## Getting Started

### Using Workflows in Your Repository

Reference workflows in your repository:

```yaml
# .github/workflows/ci.yaml
name: CI
on: [push, pull_request]

jobs:
  python-standard:
    # Current first-party consumer default
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: "3.12"

  python-pinned:
    # Pin to an exact commit for reproducible builds
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@abc123def4567890
    with:
      python-version: "3.12"
```

#### Versioning strategy

- **`@main`** – current first-party consumer default. Consumer templates and first-party repos track the latest reusable workflow behavior directly.
- **Pinned commit SHA** – use this when you need strict reproducibility or a controlled rollout.
- **Alternative refs** – use release tags or feature branches only when you are intentionally testing or managing a separate distribution strategy.

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
- Keepalive setup: templates/consumer-repo/docs/SETUP_CHECKLIST.md
- Workflow guide: docs/WORKFLOW_GUIDE.md
- Agent policy: docs/AGENTS_POLICY.md
- Compatibility: docs/COMPATIBILITY.md
- Contributing: docs/CONTRIBUTING.md
