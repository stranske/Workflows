import pathlib
import re

import yaml

ALLOWED_PREFIXES = (
    "pr-",
    "maint-",
    "agents-",
    "reusable-",
    "reuse-",
    "autofix",
    "enforce-",
    "health-",
    "selftest-",
    "debug-",
)
WORKFLOW_DIR = pathlib.Path(".github/workflows")
DOC_INVENTORY_EXEMPT_WORKFLOWS = set()


def _workflow_paths():
    return sorted(WORKFLOW_DIR.glob("*.yml"))


def _extract_name_from_lines(data: list[str]) -> str:
    name_line = next((line for line in data if line.startswith("name:")), None)
    assert name_line is not None, "Workflow missing name field"
    value = name_line.split(":", 1)[1].strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return value


def test_workflow_slugs_follow_wfv1_prefixes():
    non_compliant = [
        path.name for path in _workflow_paths() if not path.name.startswith(ALLOWED_PREFIXES)
    ]
    assert (
        not non_compliant
    ), f"Non-compliant workflow slug(s) detected outside {ALLOWED_PREFIXES}: {non_compliant}"


def test_archive_directories_removed():
    assert not (
        WORKFLOW_DIR / "archive"
    ).exists(), ".github/workflows/archive/ should be removed (tracked in docs/archive/ARCHIVE_WORKFLOWS.md)"
    legacy_dir = pathlib.Path("Old/.github/workflows")
    assert not legacy_dir.exists(), "Old/.github/workflows/ should remain deleted"


def test_docs_only_fast_path_workflow_removed():
    legacy_fast_path = WORKFLOW_DIR / "pr-14-docs-only.yml"
    assert (
        not legacy_fast_path.exists()
    ), "Legacy docs-only fast path must remain removed; Gate owns the behavior"


def test_gate_docs_only_branching_logic():
    gate_workflow = WORKFLOW_DIR / "pr-00-gate.yml"
    assert gate_workflow.exists(), "Gate workflow must remain present"

    config = yaml.safe_load(gate_workflow.read_text(encoding="utf-8"))
    jobs = config.get("jobs") or {}

    detect = jobs.get("detect") or {}
    outputs = detect.get("outputs") or {}
    assert {
        "doc_only",
        "run_core",
        "reason",
    }.issubset(outputs), "Detect job must expose doc_only, run_core, and reason outputs"

    heavy_jobs = {
        "python-ci",
        "docker-smoke",
    }
    for job_name in heavy_jobs:
        job_config = jobs.get(job_name)
        assert job_config, f"{job_name} job missing from Gate workflow"
        condition = job_config.get("if")
        assert condition, f"{job_name} job missing docs-only guard condition"
        assert (
            "needs.detect.outputs.doc_only != 'true'" in condition
        ), f"{job_name} must skip when docs-only"
        assert (
            "needs.detect.outputs.run_core == 'true'" in condition
        ), f"{job_name} must honor run_core toggle"

    gate_job = jobs.get("summary") or {}
    gate_steps = gate_job.get("steps") or []
    docs_only_steps = [
        step for step in gate_steps if isinstance(step, dict) and step.get("id") == "docs_only"
    ]
    assert docs_only_steps, "Summary job must include docs-only handling step"
    docs_only_step = docs_only_steps[0]
    assert (
        docs_only_step.get("if") == "needs.detect.outputs.doc_only == 'true'"
    ), "Docs-only step must run only for doc-only changes"

    script_block = ((docs_only_step.get("with") or {}).get("script")) or ""
    assert "require('./.github/scripts/gate-docs-only.js')" in script_block
    assert "handleDocsOnlyFastPass" in script_block

    helper_path = pathlib.Path(".github/scripts/gate-docs-only.js")
    assert helper_path.exists(), "gate-docs-only helper script must exist"
    helper_source = helper_path.read_text(encoding="utf-8")
    expected_snippets = {
        "state output": "state: 'success'",
        "description output": "description: message",
        "fast-pass message": "Gate fast-pass: docs-only change detected; heavy checks skipped.",
    }
    for label, snippet in expected_snippets.items():
        assert snippet in helper_source, f"Docs-only helper script should define {label}"


def test_health_44_pull_requests_do_not_use_repo_variable_fingerprints():
    workflow = WORKFLOW_DIR / "health-44-gate-branch-protection.yml"
    source = workflow.read_text(encoding="utf-8")

    assert '"${GITHUB_EVENT_NAME}" = "pull_request"' in source
    assert "pull-request-no-repo-variable" in source
    assert "--storage repo-variable" in source
    assert source.index("pull-request-no-repo-variable") < source.index("--storage repo-variable")


def test_health_40_sweep_permissions_cover_called_branch_protection_workflow():
    sweep = yaml.safe_load((WORKFLOW_DIR / "health-40-sweep.yml").read_text(encoding="utf-8"))
    branch_protection = yaml.safe_load(
        (WORKFLOW_DIR / "health-44-gate-branch-protection.yml").read_text(encoding="utf-8")
    )
    permission_levels = {"none": 0, "read": 1, "write": 2}
    branch_protection_job = sweep["jobs"]["branch-protection-verify"]
    caller_permissions = branch_protection_job.get("permissions") or sweep.get("permissions") or {}
    called_permissions = branch_protection.get("permissions") or {}

    for scope, requested in called_permissions.items():
        available = caller_permissions.get(scope, "none")
        assert permission_levels[available] >= permission_levels[requested], (
            "Health 40 Sweep calls Health 44 as a reusable workflow, so its effective "
            f"`{scope}` permission must be at least `{requested}`; found `{available}`."
        )


def test_health_53_scorecard_uses_existing_semver_action_ref():
    workflow = WORKFLOW_DIR / "health-53-scorecard.yml"
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    uses = [step["uses"] for step in data["jobs"]["scorecard"]["steps"] if "uses" in step]
    scorecard_refs = [action for action in uses if action.startswith("ossf/scorecard-action@")]

    assert len(scorecard_refs) == 1
    assert re.fullmatch(r"ossf/scorecard-action@v\d+\.\d+\.\d+", scorecard_refs[0])


def test_maint_83_bootstrap_uses_published_action_versions():
    workflow = WORKFLOW_DIR / "maint-83-bootstrap-consumer.yml"
    source = workflow.read_text(encoding="utf-8")
    data = yaml.safe_load(source)
    uses = [step["uses"] for step in data["jobs"]["bootstrap"]["steps"] if "uses" in step]

    assert any(
        action.startswith("actions/checkout@v") and action.rsplit("@v", 1)[1].isdigit()
        for action in uses
    )
    assert any(
        action.startswith("actions/setup-python@v") and action.rsplit("@v", 1)[1].isdigit()
        for action in uses
    )


def test_inventory_docs_list_all_workflows():
    docs = {
        "docs/ci/WORKFLOW_SYSTEM.md": pathlib.Path("docs/ci/WORKFLOW_SYSTEM.md").read_text(
            encoding="utf-8"
        ),
        "docs/ci/WORKFLOWS.md": pathlib.Path("docs/ci/WORKFLOWS.md").read_text(encoding="utf-8"),
    }

    def _listed(contents: str, slug: str) -> bool:
        options = (
            f"`{slug}`",
            f"`.github/workflows/{slug}`",
        )
        return any(option in contents for option in options)

    missing_by_doc = {
        doc_name: [
            path.name
            for path in _workflow_paths()
            if path.name not in DOC_INVENTORY_EXEMPT_WORKFLOWS and not _listed(contents, path.name)
        ]
        for doc_name, contents in docs.items()
    }
    failures = {doc: names for doc, names in missing_by_doc.items() if names}
    assert not failures, f"Workflow inventory missing entries: {failures}"


def test_workflow_names_match_filename_convention():
    mismatches = {}
    for path in _workflow_paths():
        expected = EXPECTED_NAMES.get(path.name)
        assert expected, f"Missing expected name mapping for {path.name}"
        data = path.read_text(encoding="utf-8").splitlines()
        actual = _extract_name_from_lines(data)
        if actual != expected:
            mismatches[path.name] = actual
    assert not mismatches, f"Workflow name mismatch detected: {mismatches}"


def test_workflow_display_names_are_unique():
    names_to_files: dict[str, list[str]] = {}
    for path in _workflow_paths():
        data = path.read_text(encoding="utf-8").splitlines()
        display_name = _extract_name_from_lines(data).strip()
        assert display_name, f"Workflow {path.name} missing name field"
        names_to_files.setdefault(display_name, []).append(path.name)

    duplicates = {name: files for name, files in names_to_files.items() if len(files) > 1}
    assert not duplicates, f"Duplicate workflow display names detected: {duplicates}"


EXPECTED_NAMES = {
    "agents-autofix-loop.yml": "Agents Autofix Loop",
    "agents-autofix-dispatcher.yml": "Agents Autofix Dispatch",
    "agents-auto-label.yml": "Auto-Label Issues",
    "agents-auto-pilot.yml": "Agents Auto-Pilot",
    "agents-bot-comment-handler.yml": "Agents Bot Comment Handler",
    "agents-capability-check.yml": "Capability Check",
    "agents-decompose.yml": "Task Decomposition",
    "agents-dedup.yml": "Duplicate Detection",
    "agents-guard.yml": "Health 45 Agents Guard",
    "maint-auto-label-dep-prs.yml": "Auto-label dependency PRs",
    "maint-auto-lock-deps.yml": "Auto-lock dependency PRs",
    "agents-63-issue-intake.yml": "Agents 63 Issue Intake",
    "agents-64-verify-agent-assignment.yml": "Agents 64 Verify Agent Assignment",
    "agents-issue-optimizer.yml": "Agents Issue Optimizer",
    "agents-verifier.yml": "Agents Verifier",
    "agents-verify-to-issue-v2.yml": "Create Issue from Verification (Enhanced)",
    "agents-verify-to-new-pr.yml": "Create New PR from Verification",
    "agents-weekly-metrics.yml": "agents-weekly-metrics",
    "agents-70-orchestrator.yml": "Agents 70 Orchestrator",
    "agents-moderate-connector.yml": "Agents Moderate Connector Comments",
    "agents-71-codex-belt-dispatcher.yml": "Agents 71 Codex Belt Dispatcher",
    "agents-72-codex-belt-worker-dispatch.yml": "Agents 72 Codex Belt Worker Dispatch",
    "agents-72-codex-belt-worker.yml": "Agents 72 Codex Belt Worker",
    "agents-73-codex-belt-conveyor.yml": "Agents 73 Codex Belt Conveyor",
    "agents-debug-issue-event.yml": "Agents Debug Issue Event",
    "agents-keepalive-loop.yml": "Agents Keepalive Loop",
    "agents-keepalive-sweep.yml": "Agents Keepalive Sweep",
    "agents-keepalive-loop-reporter.yml": "Keepalive Loop Reporter",
    "agents-keepalive-branch-sync.yml": "Keepalive Branch Sync",
    "agents-keepalive-dispatch-handler.yml": "Keepalive Dispatch Handler",
    # Note: agents-pr-meta.yml, v2, v3 archived to archives/github-actions/2025-12-02-pr-meta-legacy/
    "agents-pr-meta-v4.yml": "Agents PR meta manager",
    "autofix.yml": "CI Autofix Loop",
    "health-40-repo-selfcheck.yml": "Health 40 Repo Selfcheck",
    "health-40-sweep.yml": "Health 40 Sweep",
    "health-41-repo-health.yml": "Health 41 Repo Health",
    "health-42-actionlint.yml": "Health 42 Actionlint",
    "health-43-ci-signature-guard.yml": "Health 43 CI Signature Guard",
    "health-44-gate-branch-protection.yml": "Health 44 Gate Branch Protection",
    "health-codex-auth-check.yml": "Health 46 Codex Auth Check",
    "health-50-security-scan.yml": "Health 50 Security Scan",
    "health-51-zizmor.yml": "Health 51 Actions SAST (zizmor)",
    "health-52-semgrep.yml": "Health 52 Semgrep Scan",
    "health-53-scorecard.yml": "Health 53 Scorecard",
    "maint-45-cosmetic-repair.yml": "Maint 45 Cosmetic Repair",
    "maint-46-post-ci.yml": "Maint 46 Post CI",
    "maint-47-disable-legacy-workflows.yml": "Maint 47 Disable Legacy Workflows",
    "maint-48-docs-drift-audit.yml": "Maint 48 Docs Drift Audit",
    "maint-50-tool-version-check.yml": "Maint 50 Tool Version Check",
    "maint-sync-action-versions.yml": "Maint Sync Action Versions",
    "maint-sync-env-from-pyproject.yml": "Maint - Sync pyproject from versions.env",
    "maint-52-validate-workflows.yml": "Maint 52 Validate Workflows",
    "maint-52-sync-dev-versions.yml": "Maint 52 Sync Dev Versions",
    "maint-auto-update-pypi-versions.yml": "Maint Auto-Update PyPI Versions",
    "maint-62-integration-consumer.yml": "Maint 62 Integration Consumer",
    "maint-65-sync-label-docs.yml": "Maint 65 Sync Label Docs",
    "maint-66-monthly-audit.yml": "Maint 66 Monthly Audit",
    "health-67-integration-sync-check.yml": "Health 67 Integration Sync Check",
    "health-68-consumer-sync-drift.yml": "Health 68 Consumer Sync Drift Check",
    "health-70-validate-sync-manifest.yml": "Validate Sync Manifest",
    "health-71-sync-health-check.yml": "Health 71 Sync Health Check",
    "health-72-template-sync.yml": "Health 72 Template Sync",
    "health-73-template-completeness.yml": "Health 73 Template Completeness",
    "health-74-template-drift.yml": "Health 74 Template Drift",
    "health-75-api-rate-diagnostic.yml": "Health 75 API Rate Diagnostic",
    "health-76-codex-cli-freshness.yml": "Health 76 Codex CLI Freshness",
    "health-78-backplane-contract.yml": "Backplane Contract Integrity",
    "maint-68-sync-consumer-repos.yml": "Maint 68 Sync Consumer Repos",
    "maint-69-sync-integration-repo.yml": "Maint 69 Sync Integration Repo",
    "maint-69-sync-labels.yml": "Maint 69 Sync Labels",
    "maint-60-release.yml": "Maint 60 Release",
    "maint-61-release-please.yml": "Maint 61 Release Please",
    "maint-70-fix-integration-formatting.yml": "Fix Integration Tests Formatting",
    "maint-71-auto-fix-integration.yml": "Auto-Fix Integration Test Failures",
    "maint-71-merge-sync-prs.yml": "Merge Sync PRs",
    "maint-74-ledger-base-sync.yml": "Ledger Base Sync",
    "maint-80-langsmith-metrics-dashboard.yml": "LangSmith Metrics Dashboard",
    "maint-81-langsmith-fleet-conformance.yml": "LangSmith Fleet Conformance",
    "maint-82-sync-dependency-campaign.yml": "Sync/Dependency Campaign",
    "maint-83-bootstrap-consumer.yml": "Maint 83 Bootstrap Consumer",
    "maint-72-fix-pr-body-conflicts.yml": "Maint 72 Fix PR Body Conflicts",
    "maint-85-keepalive-durability-export.yml": "Maint 85 Keepalive Durability Export",
    "maint-coverage-guard.yml": "Maint Coverage Guard",
    "maint-metrics-retention.yml": "Maint Metrics Retention",
    "pr-00-gate.yml": "Gate",
    "pr-11-ci-smoke.yml": "PR 11 - Minimal invariant CI",
    "reusable-10-ci-python.yml": "Reusable CI",
    "reusable-11-ci-node.yml": "Reusable Node CI",
    "reusable-12-ci-docker.yml": "Reusable Docker Smoke",
    "reusable-13-cross-repo-smoke.yml": "Reusable Cross-Repo Smoke",
    "reusable-16-agents.yml": "Reusable 16 Agents",
    "reusable-18-autofix.yml": "Reusable 18 Autofix",
    "reusable-claude-run.yml": "Reusable Claude Run",
    "reusable-cursor-run.yml": "Reusable Cursor Run",
    "reusable-gemini-run.yml": "Reusable Gemini Run",
    "reusable-codex-run.yml": "Reusable Codex Run",
    "reusable-20-pr-meta.yml": "Reusable 20 PR Meta",
    "reusable-70-orchestrator-init.yml": "Agents 70 Init (Reusable)",
    "reusable-70-orchestrator-main.yml": "Agents 70 Main (Reusable)",
    "reusable-agents-issue-bridge.yml": "Reusable Agents Issue Bridge",
    "reusable-agents-pr-health.yml": "Reusable Agents PR Health",
    "reusable-agents-verifier.yml": "Reusable Agents Verifier",
    "reusable-bot-comment-handler.yml": "Reusable Bot Comment Handler",
    "reusable-backplane-conformance.yml": "Reusable Backplane Conformance",
    "reusable-pr-context.yml": "Reusable PR Context Fetcher",
    "selftest-reusable-ci.yml": "Selftest: Reusables",
    "selftest-ci.yml": "Selftest CI",
    "health-keepalive-e2e.yml": "Keepalive E2E",
    "maint-39-test-llm-providers.yml": "Maint 39 Test LLM Providers",
    "maint-84-prune-agent-stubs.yml": "Maint 84 Prune Agent Stubs",
}


def test_semgrep_workflow_display_name_mapping():
    """The Semgrep CE scan workflow must carry its canonical display name."""
    assert EXPECTED_NAMES["health-52-semgrep.yml"] == "Health 52 Semgrep Scan"


def test_scorecard_workflow_display_name_mapping():
    """The OpenSSF Scorecard workflow must carry its canonical display name."""
    assert EXPECTED_NAMES["health-53-scorecard.yml"] == "Health 53 Scorecard"
