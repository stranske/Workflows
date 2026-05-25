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

    for source in (
        ".github/workflows/pr-00-gate.yml",
        ".github/workflows/ci.yml",
        ".github/dependabot.yml",
    ):
        assert source in entries
        assert entries[source]["sync_mode"] == "create_only"

    for source in (
        ".github/workflows/pr-00-gate.yml",
        ".github/workflows/ci.yml",
    ):
        assert entries[source]["overwrite_repos"] == ["stranske/Template"]


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


def test_manifest_removals_include_legacy_agents_orchestrator() -> None:
    manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8")) or {}
    removals = manifest.get("removals", []) or []
    removal_targets = {entry.get("target") for entry in removals if isinstance(entry, dict)}

    assert ".github/workflows/agents-70-orchestrator.yml" in removal_targets
