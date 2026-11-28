# Repository Structure

Workflows owns the GitHub side of agent delivery and the files distributed to consumer repositories. Start with the change or symptom below. The [repository contract](../AGENTS.md) defines ownership, versioning and review expectations.

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
- Operator-run CLIs with no workflow caller, kept on purpose (re-checked 2026-11-28, round-2 E4; nothing schedules them, so run them by hand): `scripts/analyze_api_rate_limits.py` (per-token API quota report), `scripts/keepalive_metrics_dashboard.py` (dashboard from a keepalive NDJSON log), `scripts/keepalive/validate_subscription_analysis_evidence.py` (offline check of hosted subscription evidence), `scripts/fix_integration_tests_formatting.sh` (formats a Workflows-Integration-Tests checkout), `scripts/sync_pat_secrets.sh` (sets PAT secrets across repos; see the consumer setup checklist), `scripts/verify_sync_recovery.mjs` (read-only replay of a sync recovery), and the record replays `scripts/audit_followup_mutations.py` (issue 3956), `scripts/reconcile_issue_4426_coverage.py` (issue 4426), `scripts/model_eval/agy_judge_replay.py` and `scripts/model_eval/reproduce_muse13_screen.py`. Twelve others with no caller were deleted the same day.
- Coverage percentage is computed in three places on two bases: `.github/scripts/coverage-normalize.js` reads XML `line-rate` (lines only) or JSON `percent_covered`; `scripts/ci_coverage_delta.py` reads `line-rate`; `tools/coverage_guard.py` reads `percent_covered` (lines plus branches when branch coverage is on).

## Where the other material lives

| Area | What it owns |
|---|---|
| [Workflows](../.github/workflows), [actions](../.github/actions), [GitHub helpers](../.github/scripts) | GitHub event entry points, reusable jobs, composite actions and the scripts they run. The [catalog](ci/WORKFLOWS.md) lists active workflow files. |
| [Agent registry](../.github/agents), [agent instructions and prompts](../.github/codex), [configuration](../config), [required checks](../.github/config/required-contexts.json) | Agent selection, model and delivery policies, and workflow configuration. Most of `config/` by file count is frozen evaluation records, not configuration: `config/verify_paired/` (91 files) and `config/model_eval_snapshots/` (50) are read-only corpora that their tests and screens replay. The live settings are the single files at `config/` root. `.github/config/required-contexts.json` is the one source for required status checks. |
| [Consumer](../templates/consumer-repo) and [integration templates](../templates/integration-repo), [Renovate presets](../renovate-presets) | Material distributed to other repositories and the integration project that exercises shared CI. |
| [Scripts](../scripts), [tools](../tools), [packages](../packages) | See [Where code goes](#where-code-goes). For post-CI diagnostics, the [summary renderer](../tools/post_ci_summary.py) and [failure classifier](../tools/ci_failure_triage.py) belong together. Change the [GitHub comment adapter](../.github/scripts/comment-dedupe.js) for publication or marker behavior. Installable libraries have their own package entry points. |
| [Tests](../tests), [test fixtures](../tests/fixtures), [contract schemas](contracts/schemas), [autofix samples](../src/trend_analysis/README.md) | Tests own their sample inputs. Versioned formats used by running or installed software belong with the contracts. For example, the [closer schema](contracts/schemas/closer-operation-v1.schema.json) defines the format and the [minimal operation](../tests/fixtures/closer-operation/v1/minimal-operation.json) exercises it. The autofix samples deliberately contain defects. |
| [Issue task ledgers](../.agents), [stub creation](../.github/workflows/reusable-agents-issue-bridge.yml), [Claude skills](../.claude/skills), [retired PR finalizer](ops/LOCAL_LANES.md#retired-pr-finalizer) | `.agents/issue-<N>-ledger.yml` records an issue's tasks with status and commit. Gate's ledger validation checks them, and [Maint 74](../.github/workflows/maint-74-ledger-base-sync.yml) keeps their base branch current. Their writer, the Codex Belt, was retired on 2026-11-26 ([Workflows#5379](https://github.com/stranske/Workflows/pull/5379)), so the folder is a record. The issue bridge creates the optional `agents/` directory for new stubs, and the [stub maintenance workflow](../.github/workflows/maint-84-prune-agent-stubs.yml) owns eligible stub removal. |
| [Docs index](README.md), [operator guides](ops), [archived workflows](archive/ARCHIVE_WORKFLOWS.md), [archived plans](archive/ARCHIVE_PLANS.md), [historical files](archive) | Current guides, operating procedures and the history of retired workflows and superseded plans. |
| [Issue evidence](evidence) | Issue-specific acceptance records. The [shebang-rejection acceptance test](../tests/scripts/test_shebang_rejection_acceptance_run.py) reads the saved issue 3743 receipts. |
| [Reports](reports), [verification records](verification) | `docs/reports/` holds generated or audit reports, such as the cleanup tracker, workflow decisions and the CI budget. `docs/verification/` holds per-PR verification packets and the gzip text assets that the verifier captures (`docs/verification/**/*.{log,txt,xml}.gz`). |
| [Recovery evidence](../evidence) | Inputs for reconstructing earlier results. The [verifier recovery test](../tests/scripts/test_verifier_semantic_package_recovery.py) reads the issue 3820 sources and compares the recovered obligations with the recorded contract. |
| [Routing acceptance packet](#replay-routing-acceptance-evidence) | Offline recovery for the recorded routing-label result on issue 3988. |

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
