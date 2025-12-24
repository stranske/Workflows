import pathlib

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
)
WORKFLOW_DIR = pathlib.Path(".github/workflows")


def _workflow_paths():
    return sorted(WORKFLOW_DIR.glob("*.yml"))


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
        doc_name: [path.name for path in _workflow_paths() if not _listed(contents, path.name)]
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
        name_line = next((line for line in data if line.startswith("name:")), None)
        assert name_line is not None, f"Workflow {path.name} missing name field"
        actual = name_line.split(":", 1)[1].strip()
        if (actual.startswith('"') and actual.endswith('"')) or (
            actual.startswith("'") and actual.endswith("'")
        ):
            actual = actual[1:-1]
        if actual != expected:
            mismatches[path.name] = actual
    assert not mismatches, f"Workflow name mismatch detected: {mismatches}"


def test_workflow_display_names_are_unique():
    names_to_files: dict[str, list[str]] = {}
    for path in _workflow_paths():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        display_name = str(data.get("name", "")).strip()
        assert display_name, f"Workflow {path.name} missing name field"
        names_to_files.setdefault(display_name, []).append(path.name)

    duplicates = {name: files for name, files in names_to_files.items() if len(files) > 1}
    assert not duplicates, f"Duplicate workflow display names detected: {duplicates}"


EXPECTED_NAMES = {
    "agents-guard.yml": "Health 45 Agents Guard",
    "agents-63-issue-intake.yml": "Agents 63 Issue Intake",
    "agents-64-verify-agent-assignment.yml": "Agents 64 Verify Agent Assignment",
    "agents-70-orchestrator.yml": "Agents 70 Orchestrator",
    "agents-moderate-connector.yml": "Agents Moderate Connector Comments",
    "agents-71-codex-belt-dispatcher.yml": "Agents 71 Codex Belt Dispatcher",
    "agents-72-codex-belt-worker.yml": "Agents 72 Codex Belt Worker",
    "agents-73-codex-belt-conveyor.yml": "Agents 73 Codex Belt Conveyor",
    "agents-debug-issue-event.yml": "Agents Debug Issue Event",
    "agents-keepalive-loop.yml": "Agents Keepalive Loop",
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
    "health-50-security-scan.yml": "Health 50 Security Scan",
    "maint-45-cosmetic-repair.yml": "Maint 45 Cosmetic Repair",
    "maint-46-post-ci.yml": "Maint 46 Post CI",
    "maint-coverage-guard.yml": "Maint Coverage Guard",
    "maint-47-disable-legacy-workflows.yml": "Maint 47 Disable Legacy Workflows",
    "maint-50-tool-version-check.yml": "Maint 50 Tool Version Check",
    "maint-51-dependency-refresh.yml": "Maint 51 Dependency Refresh",
    "maint-52-validate-workflows.yml": "Maint 52 Validate Workflows",
    "maint-62-integration-consumer.yml": "Maint 62 Integration Consumer",
    "maint-60-release.yml": "Maint 60 Release",
    "maint-61-create-floating-v1-tag.yml": "Maint 61 Create Floating v1 Tag",
    "pr-00-gate.yml": "Gate",
    "pr-11-ci-smoke.yml": "PR 11 - Minimal invariant CI",
    "reusable-10-ci-python.yml": "Reusable CI",
    "reusable-11-ci-node.yml": "Reusable Node CI",
    "reusable-12-ci-docker.yml": "Reusable Docker Smoke",
    "reusable-16-agents.yml": "Reusable 16 Agents",
    "reusable-18-autofix.yml": "Reusable 18 Autofix",
    "reusable-codex-run.yml": "Reusable Codex Run",
    "reusable-20-pr-meta.yml": "Reusable 20 PR Meta",
    "reusable-70-orchestrator-init.yml": "Agents 70 Init (Reusable)",
    "reusable-70-orchestrator-main.yml": "Agents 70 Main (Reusable)",
    "reusable-agents-issue-bridge.yml": "Reusable Agents Issue Bridge",
    "selftest-reusable-ci.yml": "Selftest: Reusables",
    "selftest-ci.yml": "Selftest CI",
}
