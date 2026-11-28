# Repository Structure

Workflows owns the GitHub side of agent delivery and the files distributed to consumer repositories. Use the [architecture](ARCHITECTURE.md) for system boundaries and the [dependency map](ci/WORKFLOW_SYSTEM.md#topology-at-a-glance) to follow an event across workflows. Start with the change or symptom below. The [repository contract](../AGENTS.md) defines ownership, versioning and review expectations.

## Change a reusable workflow

A consumer job with `uses: stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main` runs the [shared Python CI workflow](../.github/workflows/reusable-10-ci-python.yml). Edit that workflow for shared behavior. For a caller-specific matrix or coverage setting, check the consumer's own CI configuration. First-party callers tracking `@main` receive a shared change as soon as it merges.

Check the workflow’s declared inputs, its [exported outputs](ci/WORKFLOW_OUTPUTS.md) and [consumer integration guide](INTEGRATION_GUIDE.md). For Python CI, run the [reusable workflow tests](../tests/workflows/test_reusable_ci_workflow.py) and exercise the PR revision through [Maint 62](../.github/workflows/maint-62-integration-consumer.yml). It selects scenarios against the local reusable workflow. Verify which scenarios actually ran. The [workflow topology](ci/WORKFLOWS.md) identifies callers and checks for other reusable workflows.

## Change a file distributed to consumers

Locate the target in the [sync manifest](../.github/sync-manifest.yml) and read its section, `source_tree`, `source`, `target`, mode and exceptions. For example, the consumer PR event hub comes from [its consumer template](../templates/consumer-repo/.github/workflows/agents-80-pr-event-hub.yml). Edit that source. Preserve any required root/template pairing. Change the manifest when adding, renaming, removing or changing delivery scope. The standard [PR Gate template](../templates/consumer-repo/.github/workflows/pr-00-gate.yml) is create-only by default, so existing consumers retain their own Gate policy unless the manifest declares an exception.

Use the [manifest delivery tests](../tests/workflows/test_sync_manifest_delivery.py) and [template drift checker](../scripts/check_template_drift.py) before distribution. Inspect the prospective diff in Maint 68, then verify the configured canaries and their same-plan Maint 71 evidence before promotion. Maint 71 owns sync merges. Maint 82 schedules continuations. [Consumer maintenance](ops/CONSUMER_REPO_MAINTENANCE.md) · [Sync procedure](ops/SYNC_DEPENDENCY_CAMPAIGN.md)

## Diagnose a stalled coding task

Start at the issue and linked PR. Read the opener's start comment, PR labels, current head SHA, latest Gate run, unchecked acceptance criteria and pause or human-hold labels. The required aggregate check is [`summary`](../.github/config/required-contexts.json). Use the [expected-check receipt](ops/EXPECTED_CHECK_RECEIPTS.md) when an expected check is absent or an older result looks green.

- **Local start.** A PR marked `agents:local-loop` gets its iterations from Orchestrator’s local loop. Use the [local lane contract and state locations](ops/LOCAL_LANES.md#state-locations) to find the opener target, controller/lane rounds and closer disposition. Trace the most recent action for that issue and SHA. The local loop can hand the PR to hosted keepalive.
- **Hosted start.** On a PR with `agent:*` and `agents:keepalive`, inspect the run summary and PR state comment. In Workflows, open the [Gate-triggered keepalive loop](../.github/workflows/agents-keepalive-loop.yml). In a consumer, open [Gate Followups](../templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml). If a round produced no new event, trace the [hourly sweep for that repository](keepalive/GoalsAndPlumbing.md#periodic-re-evaluation-keepalive-sweep). The [operator quick reference](QUICK_REFERENCE.md) explains holds and retry behavior.
- **After merge.** Follow the verifier evidence on the PR and the closer's disposition on the issue. A failed acceptance check may lead to a repair, follow-up or reopened issue. The [lane contract](ops/LOCAL_LANES.md#lanes-overview) identifies who acts next.

## Where code goes

Take the first rule that matches. Each file then has exactly one home.

1. **It is delivered to consumers.** If it is listed in the [sync manifest](../.github/sync-manifest.yml), it keeps its current path. Consumers receive it at that path, so moving it is a fleet migration (168 files on 2026-11-28: 94 in `.github/scripts`, 52 in `scripts`, 22 in `tools`). Root-owned `scripts/` and `tools/` files have no copy under `templates/consumer-repo/`, and `scripts/validate_template_sync.py` rejects one if it appears.
2. **`packages/`:** it is separately versioned, with its own `pyproject.toml`.
3. **`.github/scripts/`:** it only runs inside a GitHub Actions job, for example a JavaScript module loaded by `actions/github-script` or a Python helper that needs the Actions context (`GITHUB_OUTPUT`, `GITHUB_STEP_SUMMARY`, the event payload). JavaScript tests go in `.github/scripts/__tests__/`.
4. **`scripts/`:** it has an entry point (`__main__`, `python -m`, or a shell script) that a workflow step or an operator can run from a checkout. This holds even when other code imports it. Group related CLIs in a subfolder. The LangChain pipeline is in `scripts/langchain/`. The verifier research and replay CLIs are in `scripts/verifier/`. The model-evaluation and judge-screen CLIs are in `scripts/model_eval/`.
5. **`tools/`:** it has no entry point and is imported by entry points in two or more folders (for example `tools/llm_registry.py`, which `scripts/langchain/` and `tools/` both use).
6. **Next to its callers:** it has no entry point and every importer is in one folder. Put it in that folder, or in a subpackage such as `scripts/metrics/` for helpers shared by several CLIs in `scripts/`.

Tests follow the code they test. Test inputs live under `tests/fixtures/<topic>/` for Python and `.github/scripts/__tests__/fixtures/` for JavaScript. Issue evidence (`docs/evidence/`, `evidence/`) and frozen corpora (`config/verify_paired/`, `config/model_eval_snapshots/`) are records, not fixtures. A test may read a record by name, but new test inputs are not added there.

Known exceptions, kept on purpose or tracked:
- `templates/consumer-repo/scripts/check_deliberate_break.py` is a byte-checked copy, because the issue-3743 replays bind its path.
- Delivered CLIs still in `tools/` (for example `coverage_guard.py`) stay there under rule 1.
- Undelivered `tools/` CLIs that rule 4 would move: `enforce_gate_branch_protection.py`, `codex_session_analyzer.py`, `codex_jsonl_parser.py`, `ensure_workflow_timeout_variables.py`, `integration_repo.py`, `test_failure_signature.py`, and the Maint 89 shadow tools (`verifier_shadow_*.py`). The verifier steps that consumer runs execute from `.workflows-lib/tools/` (`verifier_corpus_evidence.py`, `verifier_event_recovery.py`, `verifier_retained_origin.js`) are also listed here; they move only with a canary.
- Operator-run CLIs with no workflow caller, kept on purpose (re-checked 2026-11-28, round-2 E4; nothing schedules them, so run them by hand): `scripts/analyze_api_rate_limits.py` (per-token API quota report), `scripts/keepalive/validate_subscription_analysis_evidence.py` (offline check of hosted subscription evidence), `scripts/fix_integration_tests_formatting.sh` (formats a Workflows-Integration-Tests checkout), `scripts/sync_pat_secrets.sh` (sets PAT secrets across repos; see the consumer setup checklist), `scripts/verify_sync_recovery.mjs` (read-only replay of a sync recovery), and the record replays `scripts/reconcile_issue_4426_coverage.py` (issue 4426), `scripts/model_eval/agy_judge_replay.py` and `scripts/model_eval/reproduce_muse13_screen.py`. Twelve others with no caller were deleted the same day.
- The [issue #3956 manual replay](evidence/issue-3956/authoritative-reconciliation.md#current-manual-replay) lives beside the retained mutation receipts.
- Coverage percentage is computed in three places on two bases: `.github/scripts/coverage-normalize.js` reads XML `line-rate` (lines only) or JSON `percent_covered`; `scripts/ci_coverage_delta.py` reads `line-rate`; `tools/coverage_guard.py` reads `percent_covered` (lines plus branches when branch coverage is on).

For current keepalive terminal records, use [Agents Weekly Metrics](../.github/workflows/agents-weekly-metrics.yml),
which summarizes them with [the weekly collector](../scripts/aggregate_agent_metrics.py).
For older iteration logs that the retired dashboard supported, run this from a full Workflows checkout
to recover the CLI, its helpers and its unit tests in a scratch directory.

```sh
recovery_dir="$(mktemp -d)"
git archive dc5da58d8a943dbc5900d3346c3706dcbb17ad5e \
  scripts/keepalive_metrics_dashboard.py scripts/metrics scripts/metrics_format_utils.py \
  tests/scripts/test_keepalive_metrics_dashboard_unit.py | tar -x -C "$recovery_dir"
```

## Where the other material lives

| Area | What it owns |
|---|---|
| [Workflows](../.github/workflows), [actions](../.github/actions), [GitHub helpers](../.github/scripts) | GitHub event entry points, reusable jobs, composite actions and the scripts they run. The [catalog](ci/WORKFLOWS.md) lists active workflow files. |
| [Agent registry](../.github/agents), [agent instructions and prompts](../.github/codex), [configuration](../config), [required checks](../.github/config/required-contexts.json) | Agent selection, model and delivery policies, and workflow configuration. Most of `config/` by file count is frozen evaluation records, not configuration: `config/verify_paired/` (91 files) and `config/model_eval_snapshots/` (50) are read-only corpora that their tests and screens replay. The live settings are the single files at `config/` root. `.github/config/required-contexts.json` is the one source for required status checks. |
| [Consumer](../templates/consumer-repo) and [integration templates](../templates/integration-repo), [Renovate presets](../renovate-presets) | Material distributed to other repositories and the integration project that exercises shared CI. |
| [Scripts](../scripts), [tools](../tools), [packages](../packages) | See [Where code goes](#where-code-goes). For post-CI diagnostics, the [summary renderer](../tools/post_ci_summary.py) and [failure classifier](../tools/ci_failure_triage.py) belong together. Change the [GitHub comment adapter](../.github/scripts/comment-dedupe.js) for publication or marker behavior. Installable libraries have their own package entry points. |
| [Tests](../tests), [test fixtures](../tests/fixtures), [contract schemas](contracts/schemas), [autofix sample](../tests/fixtures/autofix/README.md) | Tests own their sample inputs. Versioned formats used by running or installed software belong with the contracts. For example, the [closer schema](contracts/schemas/closer-operation-v1.schema.json) defines the format and the [minimal operation](../tests/fixtures/closer-operation/v1/minimal-operation.json) exercises it. The autofix sample deliberately contains a defect. |
| [Issue task ledgers](../.agents), [stub creation](../.github/workflows/reusable-agents-issue-bridge.yml), [Claude skills](../.claude/skills), [retired PR finalizer](ops/LOCAL_LANES.md#retired-pr-finalizer) | `.agents/issue-<N>-ledger.yml` records an issue's tasks with status and commit. Gate's ledger validation checks them, and [Maint 74](../.github/workflows/maint-74-ledger-base-sync.yml) keeps their base branch current. Their writer, the Codex Belt, was retired on 2026-11-26 ([Workflows#5379](https://github.com/stranske/Workflows/pull/5379)), so the folder is a record. The issue bridge creates the optional `agents/` directory for new stubs, and the [stub maintenance workflow](../.github/workflows/maint-84-prune-agent-stubs.yml) owns eligible stub removal. |
| [Docs index](README.md), [operator guides](ops), [archived workflows](archive/ARCHIVE_WORKFLOWS.md), [archived plans](archive/ARCHIVE_PLANS.md), [historical files](archive) | Current guides, operating procedures and the history of retired workflows and superseded plans. |
| [Issue evidence](evidence) | Issue-specific acceptance records. The [historical deliberate-break index](archive/audits/DELIBERATE_BREAK_RECEIPTS.md) links the original mutation and recovery results. The [shebang-rejection acceptance test](../tests/scripts/test_shebang_rejection_acceptance_run.py) reads the saved issue 3743 receipts. |
| [Reports](reports), [verification records](verification) | `docs/reports/` holds generated or audit reports, such as the cleanup tracker, workflow decisions and the CI budget. `docs/verification/` holds per-PR verification packets and the gzip text assets that the verifier captures (`docs/verification/**/*.{log,txt,xml}.gz`). |
| [Recovery evidence](../evidence) | Inputs for reconstructing earlier results. The [verifier recovery test](../tests/scripts/test_verifier_semantic_package_recovery.py) reads the issue 3820 sources and compares the recovered obligations with the recorded contract. |
| [Routing acceptance packet](#replay-routing-acceptance-evidence) | Offline recovery for the recorded routing-label result on issue 3988. |

## Directory index

Every top-level and second-level directory, one line each. This is the only layout map:
the [main README](../README.md) and the [docs index](README.md) link here, and
`tests/docs/test_structure_directory_index.py` fails when a directory is added, removed
or renamed without updating this list.

| Directory | Holds |
|---|---|
| `.agents/` | Issue task ledgers (`issue-<N>-ledger.yml`); a record since the Codex Belt retired |
| `.claude/` | Claude Code project settings |
| `.claude/skills/` | Claude skills used in this repository |
| `.devcontainer/` | Dev container definition |
| `.github/` | GitHub configuration, workflows, actions and the scripts they run |
| `.github/ISSUE_TEMPLATE/` | Issue forms and agent-task templates |
| `.github/actions/` | Composite actions, one `action.yml` each, plus pinned CLI installs |
| `.github/agents/` | Agent registry and model table |
| `.github/codex/` | Agent instructions and prompts |
| `.github/config/` | Required status checks (`required-contexts.json`) |
| `.github/copilot-skills-local/` | Local Copilot skill notes |
| `.github/scripts/` | Code that runs inside Actions jobs; JavaScript tests in `__tests__/` |
| `.github/signature-fixtures/` | Inputs for the signature-verify action's self-test |
| `.github/templates/` | Instruction text that workflows post (keepalive instruction) |
| `.github/workflows/` | Workflow entry points and reusable workflows ([catalog](ci/WORKFLOWS.md)) |
| `agents/` | Optional issue stubs created by the issue bridge |
| `config/` | Live settings (single files at the root) and frozen evaluation corpora |
| `config/model_eval_snapshots/` | Frozen model-evaluation snapshots (record) |
| `config/verify_paired/` | Frozen paired-verification corpus (record) |
| `docs/` | Documentation ([index](README.md)) |
| `docs/analysis/` | One-off evaluations (record) |
| `docs/archive/` | Retired workflows, superseded plans and historical files |
| `docs/ci/` | CI reference: workflow catalog, outputs, audit procedure |
| `docs/closer-operation/` | Closer operation contract and local validation |
| `docs/contracts/` | Cross-repo contracts and JSON schemas |
| `docs/dashboards/` | Dashboard notes (LangSmith metrics) |
| `docs/evidence/` | Issue acceptance evidence (record) |
| `docs/exports/` | Exported skill text |
| `docs/fixes/` | Remediation plans and audits (record) |
| `docs/git-hooks/` | Git hook overview |
| `docs/guides/` | How-to guides (adding an agent) |
| `docs/keepalive/` | Keepalive contract and agent routing |
| `docs/ops/` | Operating procedures (lanes, sync, consumer maintenance, runbook) |
| `docs/orchestrator/` | Orchestrator-facing maps and plans |
| `docs/plans/` | Plans (mostly superseded; see the archive) |
| `docs/reference/` | Reference notes |
| `docs/reports/` | Generated and audit reports (cleanup tracker, decisions, CI budget) |
| `docs/reverification/` | Reverification decisions for missing artifacts (record) |
| `docs/templates/` | Issue and setup templates |
| `docs/validation/` | Validation overview |
| `docs/verification/` | Per-PR verification packets and captured assets (record) |
| `docs/workflow-snippets/` | Copyable workflow fragments |
| `docs/workflow-updates/` | Workflow review notes (record) |
| `docs/workflows/` | Workflow system notes (evaluation, bug report) |
| `evidence/` | Recovery inputs kept per issue, separate from `docs/evidence` |
| `evidence/issue-<number>/` | One issue's recovery inputs (record) |
| `packages/` | Separately versioned packages |
| `packages/app-baseline-kit/` | App baseline kit package |
| `packages/stranske_pdf_extract/` | PDF extraction package |
| `renovate-presets/` | Renovate presets for the fleet, including the generated consumer-managed paths |
| `scripts/` | CLIs with an entry point ([Where code goes](#where-code-goes), rule 4) |
| `scripts/keepalive/` | Keepalive evidence validator |
| `scripts/langchain/` | LangChain issue pipeline (formatter, optimizer, decomposer) |
| `scripts/metrics/` | Metrics helpers shared by `scripts/*metrics*` CLIs |
| `scripts/model_eval/` | Model-evaluation and judge-screen CLIs |
| `scripts/repo_review_publication/` | Repo-review publication helpers |
| `scripts/runner_lib/` | Runner library (acceptance gate) |
| `scripts/verifier/` | Verifier research and replay CLIs |
| `templates/` | Material distributed to other repositories |
| `templates/consumer-repo/` | Consumer template, delivered through the sync manifest |
| `templates/integration-repo/` | Integration project that exercises shared CI (Maint 62, Maint 69 to WIT) |
| `templates/test_helpers/` | Test helper module for templates |
| `templates/workflow-templates/` | GitHub starter-workflow template |
| `tests/` | Python tests; they follow the code they test |
| `tests/contracts/` | Contract and schema tests |
| `tests/docs/` | Documentation consistency tests |
| `tests/fixtures/` | Python test inputs, by topic |
| `tests/integration/` | Integration tests |
| `tests/langchain/` | Tests for `scripts/langchain/` |
| `tests/metrics/` | Tests for `scripts/metrics/` and metrics CLIs |
| `tests/scripts/` | Tests for `scripts/` |
| `tests/tools/` | Tests for `tools/` |
| `tests/workflows/` | Workflow contract tests |
| `tools/` | Importable shared modules and delivered tools ([Where code goes](#where-code-goes), rule 5) |

## Replay routing acceptance evidence

The [issue 3988 acceptance packet](https://github.com/stranske/Workflows/tree/e1b5c5284108b94eacaab658cfcc60196c2dd0ce/artifacts/issue-3988) is preserved at its immutable revision. [Issue 4515](https://github.com/stranske/Workflows/issues/4515) cites the original paths and commands.

Recover the packet in a disposable Git directory and run the recorded replay with the repository-selected Python.

```sh
replay_dir=$(mktemp -d)
packet_rev=e1b5c5284108b94eacaab658cfcc60196c2dd0ce
roster_rev=3e7f75d3750e54a1453cf9ea0ce4ed048bf24288
git init -q "$replay_dir"
git -C "$replay_dir" fetch --depth=1 https://github.com/stranske/Workflows.git "$packet_rev" "$roster_rev"
git -C "$replay_dir" checkout "$packet_rev" -- artifacts/issue-3988
(
  cd "$replay_dir"
  python -B -m unittest discover -s artifacts/issue-3988 -p test_collect_observations.py
  python -B artifacts/issue-3988/collect_observations.py --from-saved
)
```

The fetch acquires both the packet and the Git revision that defines its roster. For offline recovery, replace the remote URL with a local Workflows repository containing both revisions. Replay uses the saved histories and rewrites the report in the disposable directory. The recorded result is 17 of 51 with complete coverage.
