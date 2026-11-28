# Workflows

[![Maint 62 Integration Consumer](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml/badge.svg)](https://github.com/stranske/Workflows/actions/workflows/maint-62-integration-consumer.yml)
[![Integration Tests](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml/badge.svg)](https://github.com/stranske/Workflows-Integration-Tests/actions/workflows/ci.yml)

A reusable GitHub Actions workflow system for Python projects with integrated agent automation (Codex keepalive, autofix, CI orchestration).

For a narrative of how the repo evolved through five development phases (bootstrap → v1.1.x → Feb consolidation → production quiet → re-engagement) and where it stands today, see [`docs/HISTORY.md`](docs/HISTORY.md).

## Project Status

✅ **Production Ready** - Actively used and maintained.

### Delivery-lane expected-check receipts

Run the shared [exact-head reporter](scripts/check_checks_reported.py) before
interpreting a green check list as complete. Workflows owns this local adapter;
Orchestrator owns the [incumbent presence reporter](https://github.com/stranske/Orchestrator/blob/main/scripts/check_checks_reported.py).
The adapter extends it through its existing paginated transport; it does not copy or
replace that reporter's historical frequency/ratchet algorithm.

```bash
python3 scripts/check_checks_reported.py --repo stranske/Orchestrator --pr 461 \
  --head FULL_HEAD_SHA --event pull_request --action synchronize \
  --presence-reporter /path/to/Orchestrator/scripts/check_checks_reported.py \
  --output /path/to/evidence/Orchestrator-461-checks.json
```

For a Workflows-only invocation, replace `--presence-reporter ...` with
`--transport native-gh`. This uses a bounded read-only paginated `gh` transport
and the same topology producer, without importing Orchestrator.

Replace `FULL_HEAD_SHA` with the PR's current 40-character commit SHA before running.
Delivery lanes invoke this adapter command; the incumbent's standalone `--pr N`
command reports historical presence only. The receiving lanes are identified in
the [shared source boundary](docs/ops/EXPECTED_CHECK_RECEIPTS.md#shared-source-boundary).

The output records full head/base, event/action, changed paths, authored workflow
topology, required branch/ruleset contexts, complete check/suite pages and latest
workflow attempts. Exit codes are PASS=0, FAIL=1 and UNKNOWN=2. Unsupported or
inaccessible topology stays UNKNOWN; the receipt never authorizes a merge.
Both normalized path inventories and the closing PR context are retained;
`request_evidence` records page counts and hashes, not raw paginated file inventories.
A changed base branch, file count or path inventory also invalidates the receipt,
even when the head and base SHAs remain equal.
The incumbent file digest is retained even when loading or discovery fails;
changing that file during collection invalidates the receipt as UNKNOWN.
Unsupported event/action values also emit UNKNOWN; a typo cannot establish a
legitimate absence. Supported actions follow GitHub's
[pull request activity types](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).
Before a merge, the receiving lane must independently verify passing expected
and required checks, zero active non-outdated unresolved review threads, and
at least seven minutes elapsed for that unchanged full head.
See [the supported context and evidence contract](docs/ops/EXPECTED_CHECK_RECEIPTS.md).

### First-party Consumers

16 repos are currently registered as first-party consumers (synced via [`.github/workflows/maint-68-sync-consumer-repos.yml`](.github/workflows/maint-68-sync-consumer-repos.yml)):

- [Travel-Plan-Permission](https://github.com/stranske/Travel-Plan-Permission)
- [Template](https://github.com/stranske/Template)
- [trip-planner](https://github.com/stranske/trip-planner)
- [Manager-Database](https://github.com/stranske/Manager-Database)
- [Portable-Alpha-Extension-Model](https://github.com/stranske/Portable-Alpha-Extension-Model)
- [Trend_Model_Project](https://github.com/stranske/Trend_Model_Project)
- [Counter_Risk](https://github.com/stranske/Counter_Risk)
- [Pension-Data](https://github.com/stranske/Pension-Data)
- [Inv-Man-Intake](https://github.com/stranske/Inv-Man-Intake)
- [Ready](https://github.com/stranske/Ready)
- [learning-management-system](https://github.com/stranske/learning-management-system)
- [Fine-Art-Archive](https://github.com/stranske/Fine-Art-Archive)
- [Orchestrator](https://github.com/stranske/Orchestrator)
- [Doc-Lineage](https://github.com/stranske/Doc-Lineage)
- [Deliverable-Render](https://github.com/stranske/Deliverable-Render)
- [Manager-Mosaic](https://github.com/stranske/Manager-Mosaic)

[`.github/workflows/maint-68-sync-consumer-repos.yml`](.github/workflows/maint-68-sync-consumer-repos.yml) is the authoritative list — `REGISTERED_CONSUMER_REPOS` env var. Direct owner exclusions are applied before discovery, delivery, and campaign accounting; excluded repositories resume only after explicit owner reinstatement. The [Workflows-Integration-Tests](https://github.com/stranske/Workflows-Integration-Tests) harness validates the consumer surface separately.

Consumer delivery is coalesced into one stable PR per repository and lane:
configured canaries use `sync/workflows-candidate`, while promoted consumers use
`sync/workflows-delivery`. Maint 68 updates those ready-for-review PRs in place;
Maint 71 is the sole merger of sync PRs and advances them from labeled staging to an
exact-head seal and merge. The active review path is set by `generated_delivery_review`
in [`config/consumer_sync_review_policy.json`](config/consumer_sync_review_policy.json),
currently `integration-only`: Maint 71 sends the immutable generated payload straight
to consumer CI and Gate checks without requesting another general review or waiting
through a synthetic review interval, and records `integration_checks_required` rather
than a reviewer PASS. Required CI and Gate checks still pass on the exact head, every
active review finding still needs an explicit owner disposition, and the merge stays
bound to the exact head, source, and plan.

The legacy bounded-reviewer-settlement path applies only when `generated_delivery_review`
is absent. In that mode review capacity cannot require all configured bots: one response
is sufficient after the quiet period, and a bounded timeout keeps an unavailable reviewer
from making delivery immortal. Explicit review-skip, not-reviewed, and capacity statuses
do not count as the one response.

## Agent Pipeline

Auto-Pilot, the former single-label pipeline, was retired in #5379. Work now moves through
separate, event-driven pieces, and the three local lanes drive it (see
[`docs/ops/LOCAL_LANES.md`](docs/ops/LOCAL_LANES.md)):

```
Issue filed ──▶ Format guard / optimizer ──▶ Opener lane starts an agent ──▶ Agent PR
                (agents:format, agents:optimize)   (hosted keepalive or local)     │
                                                                                   ▼
        Follow-up issue ◀── CONCERNS/FAIL ◀── Verify ◀── Merge ◀── Keepalive + Gate
                                                │ PASS
                                                ▼
                                          Closer lane closes the issue
```

| Stage | What happens | Owner |
|-------|--------------|-------|
| **Format / optimize** | `issue_formatter.py`, `task_decomposer.py` and `issue_optimizer.py` restructure the issue into Why / Scope / Tasks / Acceptance Criteria and add file paths. A body that does not validate gets `agents:auto-pilot-pause` (the format-guard hold; the name is kept from Auto-Pilot) until the opener lane rewrites it | `agents-issue-format-guard.yml`, `agents-issue-optimizer.yml` |
| **Start** | The opener lane picks the agent and mode from the `agent:*` label and the registry, then starts hosted keepalive or a local delegate | opener lane |
| **Keepalive** | Event-driven loop: Gate completion → task appendix → registry-backed agent dispatch → push → repeat | `agents-81-gate-followups.yml` (consumers), keepalive loop (this repo) |
| **Merge, verify, close** | The closer lane merges green PRs, applies `verify:compare`, reads the verdict, files bounded follow-ups, and closes the issue | closer lane, `agents-verifier.yml` |
| **Follow-up** | On CONCERNS/FAIL, `verify:create-issue` makes an issue-only follow-up and `verify:create-new-pr` a bootstrapped follow-up PR; the new-PR path enforces the chain-depth cap. Both label follow-ups through `verification_followup_labels.js` | `agents-verify-to-issue-v2.yml`, `agents-80-pr-event-hub.yml` |

### Key Design Decisions

- **Event-driven keepalive** — Gate `workflow_run` completion triggers iteration, not polling
- **Task appendix injection** — Agent prompts include explicit, structured task context from the issue
- **Token-aware retry** — `withRetry` + `token_load_balancer.js` distributes API calls across PATs and GitHub App tokens
- **Verification pipeline** — Dual-model `verify:compare` catches quality gaps post-merge; see metrics below

### Verification Pipeline

After PR merge, applying a `verify:*` label (`verify:compare` for dual-model mode, which the closer lane applies to merged agent PRs, or `verify:evaluate`, which a person applies by hand) triggers the verifier. In `compare` mode, the configured LLM providers (gpt-6.1-sol + claude-sonnet-5-5) evaluate the diff against acceptance criteria. The default `evidence_profile=standard` aggregates the available result rows without requiring both configured provider slots to be present: a single completed judge can yield PASS. Reported FAIL/CONCERNS verdicts, unavailable/error results, and CI/evidence floors still withhold PASS. A standard PASS alone does not prove two judges ran. Explicit dispatch recovery with `evidence_profile=expanded` requires a complete, error-free boolean `used_llm=true` PASS from both provider slots. Expanded recovery is eligible only after a real verifier truncation report, as described in the [workflow guide](docs/WORKFLOW_GUIDE.md#how-to-trigger-verification). A PASS does not prove the reports contain no advisory concerns. Operators must inspect both provider results before claiming dual-model acceptance. On CONCERNS or FAIL, maintainers or automation can apply the `verify:create-new-pr` label to trigger a 4-round LLM pipeline that generates a follow-up issue (analyze -> tasks -> acceptance criteria -> format).

**Live verifier and pipeline metrics** are surfaced through the weekly summary tracker — see [issue #2211](https://github.com/stranske/Workflows/issues/2211) (durable auto-bot tracker, posted Mondays at 06:00 UTC) and the [LangSmith dashboard issue #2415](https://github.com/stranske/Workflows/issues/2415), generated by [`maint-80-langsmith-metrics-dashboard.yml`](.github/workflows/maint-80-langsmith-metrics-dashboard.yml). The workflow publishes to the durable issue and retained artifacts rather than pushing generated files to `main`. The original Feb 2026 baseline (40-PR sample, first-fix 35%, avg chain depth 2.7) is preserved at [`docs/analysis/verify-compare-40pr-evaluation-feb-2026.md`](docs/analysis/verify-compare-40pr-evaluation-feb-2026.md) for historical comparison.

---

## What's Included

### Reusable Workflows (.github/workflows)

- CI: `reusable-10-ci-python.yml`, `reusable-11-ci-node.yml`, `reusable-12-ci-docker.yml`, `reusable-13-cross-repo-smoke.yml`
- Agent automation: `reusable-18-autofix.yml`, `reusable-19-dependency-repair-contract.yml`, `reusable-20-pr-meta.yml`, `reusable-codex-run.yml`, `reusable-model-profile-trial.yml`, `reusable-claude-run.yml`, `reusable-cursor-run.yml`, `reusable-gemini-run.yml`, `reusable-muse-run.yml`
- Agent helpers: `reusable-agents-issue-bridge.yml`, `reusable-agents-pr-health.yml`, `reusable-agents-verifier.yml`, `reusable-bot-comment-handler.yml`, `reusable-pr-context.yml`
- Conformance: `reusable-backplane-conformance.yml`

### First-party Orchestration Workflows (.github/workflows)

- Gate: `pr-00-gate.yml` (single PR-required check)
- Maintenance & health: `maint-*`, `health-*`
- Agents: `agents-*` (verifier, keepalive, issue-intake, pr-meta, issue format guard and optimizer)
- Model-profile canary: `agents-model-profile-trial.yml` dispatches exactly one
  pinned, read-only Astra/Sol/Terra/Luna arm and uploads quarantine-only identity
  telemetry. It cannot commit, push, comment, refresh auth, or score the arm.

### Composite Actions (.github/actions)

Fourteen composite actions, each with an `action.yml`:

- `agent-event-eligibility/` - Decide whether an agent workflow event warrants running before expensive setup
- `agent-reference-packs/` - Validate and materialize reference packs for reusable agent runners
- `agent-run-base/` - Shared setup for the reusable agent runner workflows (checkout, Node, API client, Workflows scripts)
- `artifact-cache/` - Restore, discover, and cache workflow artifacts by run window
- `auth-alert-issue/` - Open, update or close the alert issue for an agent auth check
- `autofix/` - Formatting and hygiene automation
- `build-pr-comment/` - Assemble the autofix status comment from residual reports and trend artifacts
- `codex-bootstrap-lite/` - Lightweight issue → branch → PR bootstrap for agent runs
- `export-load-balancer-tokens/` - Export token rotation secrets for the token load balancer
- `generated-delivery-seal/` - Enforce the stable sync-delivery seal from Workflows-owned code
- `path-classifier/` - Classify changed PR paths into workflow relevance categories
- `resolve-default-branch/` - Resolve a repository default branch with the shared retry helper
- `setup-api-client/` - Token export and API client initialization
- `signature-verify/` - Signature/manifest verification helpers

Three more folders hold pinned CLI installs (`package.json` + lockfile, no `action.yml`):
`maint78-codex-cli/`, `trial-codex-cli/`, `verifier-codex-cli/`.

### Other Top-level Code Homes

- `tools/` - shared importable Python modules (the LLM library, files delivered to consumers) plus research CLIs for the verifier and model evaluation
- `src/` - four metrics modules used by `scripts/*metrics*`, and deliberately broken autofix samples (`src/trend_analysis/`) that the fleet path classifier names
- `packages/` - versioned packages (`app-baseline-kit`, `stranske_pdf_extract`)
- `evidence/` - records kept per issue (`evidence/issue-<number>/`), separate from `docs/evidence`

### Scripts

**Validation (`scripts/`):**
- `check_branch.sh` - Comprehensive branch validation
- `validate_workflow_yaml.py` - Workflow YAML syntax checking
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
- `docs/GLOSSARY.md` — plain-language definitions of the system's key terms
- `docs/QUICK_REFERENCE.md` — two-page operator cheat-sheet (pause/resume, keepalive, labels)
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
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  python-standard:
    # Current first-party consumer default
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main
    with:
      python-version: "3.14"

  python-pinned:
    # Pin to an exact commit for reproducible builds
    uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@abc123def4567890
    with:
      python-version: "3.14"
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

Use the [repository map](docs/STRUCTURE.md) to find the source for a [shared workflow change](docs/STRUCTURE.md#change-a-reusable-workflow), [a file distributed to consumers](docs/STRUCTURE.md#change-a-file-distributed-to-consumers), or [a stalled coding task](docs/STRUCTURE.md#diagnose-a-stalled-coding-task).

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
- Glossary: docs/GLOSSARY.md
- Quick reference: docs/QUICK_REFERENCE.md
- Usage: docs/USAGE.md
- Integration guide: docs/INTEGRATION_GUIDE.md
- CI wiring: docs/ci-workflow.md
- Keepalive setup: templates/consumer-repo/docs/SETUP_CHECKLIST.md
- Workflow guide: docs/WORKFLOW_GUIDE.md
- Agent policy: docs/AGENTS_POLICY.md
- Compatibility: docs/COMPATIBILITY.md
- Contributing: docs/CONTRIBUTING.md
