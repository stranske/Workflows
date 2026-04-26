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


def test_consumer_sync_pr_body_surfaces_create_only_skips() -> None:
    workflow = SYNC_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "sync_mode == 'create_only'" in workflow
    assert "File exists and sync_mode is create_only" in workflow
    assert "### Files Skipped" in workflow
    assert 'f.write(f"- {s}\\n")' in workflow
    assert "sync_summary.md" in workflow
