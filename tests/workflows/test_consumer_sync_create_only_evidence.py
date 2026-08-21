import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / ".github" / "sync-manifest.yml"
SYNC_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml"


def _manifest_entries() -> dict[str, dict]:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    entries: dict[str, dict] = {}
    for section in ("workflows", "scripts", "docs", "prompts", "codex_config"):
        for item in manifest.get(section, []) or []:
            source = item.get("source")
            if source:
                entries[source] = item
    return entries


def test_consumer_create_only_files_are_manifested() -> None:
    entries = _manifest_entries()

    # Consumer-specific bootstrap files must be seeded without clobbering repos
    # that already customized their local configuration.
    for source in (
        ".github/workflows/pr-00-gate.yml",
        ".github/workflows/ci.yml",
        ".github/renovate.json",
    ):
        assert source in entries
        assert entries[source]["sync_mode"] == "create_only"

    for source in (
        ".github/workflows/pr-00-gate.yml",
        ".github/workflows/ci.yml",
    ):
        assert entries[source]["overwrite_repos"] == ["stranske/Template"]

    # .github/dependabot.yml was intentionally dropped from the template and the
    # manifest in #2401 (P3b of the Renovate fleet migration): create_only sync
    # would otherwise resurrect Dependabot on every re-sync. It must no longer be
    # manifested.
    assert ".github/dependabot.yml" not in entries


def test_consumer_renovate_template_extends_fleet_preset() -> None:
    template = yaml.safe_load(
        (REPO_ROOT / "templates/consumer-repo/.github/renovate.json").read_text(encoding="utf-8")
    )

    assert template["extends"] == ["github>stranske/Workflows//renovate-presets/fleet"]


def test_fine_art_archive_jsonschema_renovate_exception_is_repo_scoped() -> None:
    preset = json.loads((REPO_ROOT / "renovate-presets/fleet.json").read_text(encoding="utf-8"))

    matching_rules = [
        rule
        for rule in preset["packageRules"]
        if rule.get("matchRepositories") == ["stranske/Fine-Art-Archive"]
        and rule.get("matchPackageNames") == ["jsonschema"]
    ]

    assert matching_rules == [
        {
            "description": "Fine-Art-Archive currently supports jsonschema below 4.23.0; do not reopen incompatible non-major bumps",
            "matchRepositories": ["stranske/Fine-Art-Archive"],
            "matchPackageNames": ["jsonschema"],
            "allowedVersions": "<4.23.0",
        }
    ]


def test_gate_manifest_entry_documents_fresh_consumer_bootstrap_risk() -> None:
    entries = _manifest_entries()
    gate = entries[".github/workflows/pr-00-gate.yml"]

    description = str(gate.get("description", ""))
    assert "not yet fresh-consumer deployable" in description
    assert "#2158" in description


def test_consumer_sync_pr_body_surfaces_create_only_skips() -> None:
    workflow = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "sync_mode == 'create_only'" in workflow
    assert "repo_overwrites_create_only" in workflow
    assert "isinstance(overwrite_repos, list)" in workflow
    assert "File exists and sync_mode is create_only" in workflow
    assert "### Files Skipped" in workflow
    assert 'f.write(f"- {s}\\n")' in workflow
    assert "sync_summary.md" in workflow


def test_maint68_applies_managed_gitignore_block_before_has_changes() -> None:
    """maint-68 must evaluate apply_block_to_file on dry_run and live paths alike."""
    workflow = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "from scripts.sync_status_file_ignores import apply_block_to_file" in workflow
    assert "dry_run=dry_run" in workflow
    assert "gitignore_result = apply_block_to_file(" in workflow
    assert "plan_scope = os.environ.get('PLAN_SCOPE', '')" in workflow
    assert "if plan_scope == 'full':" in workflow
    # Regression: do not gate the apply call behind `if not dry_run` — that hid
    # .gitignore-only drift from dry consumer runs (has_changes stayed false).
    apply_idx = workflow.index("gitignore_result = apply_block_to_file(")
    preceding = workflow[max(0, apply_idx - 200) : apply_idx]
    assert "if not dry_run:" not in preceding
    assert "has_changes = bool(changes) if dry_run else repo_dirty" in workflow
    assert ".gitignore (managed block" in workflow


def test_manifest_removals_include_legacy_agents_orchestrator() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    removals = manifest.get("removals", []) or []
    removal_targets = {entry.get("target") for entry in removals if isinstance(entry, dict)}

    assert ".github/workflows/agents-70-orchestrator.yml" in removal_targets
