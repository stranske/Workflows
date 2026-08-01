"""Contract tests for the generated consumer Renovate ownership preset.

The preset must stay derived from the live `.github/sync-manifest.yml`: if a new
overwrite-managed path appears there and the preset is not regenerated, consumer
Renovate starts opening PRs that the next Maint 68 sync silently reverts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from scripts.generate_consumer_renovate_ownership import (
    SOURCE_REPO,
    build_preset,
    is_overwrite_managed,
    main,
    match_pattern,
    render,
)
from scripts.list_registered_consumer_repos import extract_repos
from scripts.sync_manifest_compiler import compile_manifest

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / ".github" / "sync-manifest.yml"
SYNC_WORKFLOW = ROOT / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml"
PRESET = ROOT / "renovate-presets" / "consumer-managed-paths.json"
FLEET_PRESET = ROOT / "renovate-presets" / "fleet.json"

# The two paths from the issue's cited incident: consumer Renovate opened PRs
# against them (Inv-Man-Intake#838, Manager-Database#1347) and both were closed
# unmerged because Maint 68 owns the files.
INCIDENT_PATHS = (
    ".github/workflows/agents-guard.yml",
    ".github/workflows/maint-76-claude-code-review.yml",
)


def committed_preset() -> dict:
    return json.loads(PRESET.read_text(encoding="utf-8"))


def disabled_paths(preset: dict, repo: str) -> set[str]:
    """Return the effective disabled-path set for one repo.

    Every rule in the preset disables, so the rules are additive and a repo's
    effective set is the union of the rules whose matchRepositories include it.
    """
    paths: set[str] = set()
    for rule in preset["packageRules"]:
        assert rule["enabled"] is False, "every generated rule must disable, never re-enable"
        if repo in rule["matchRepositories"]:
            paths.update(rule["matchFileNames"])
    return paths


def registered_consumers() -> list[str]:
    return extract_repos(SYNC_WORKFLOW)


def expected_managed(repo: str) -> set[str]:
    entries = compile_manifest(MANIFEST, repo_root=ROOT).all_entries()
    return {match_pattern(e) for e in entries if is_overwrite_managed(e, repo)}


def write_manifest(tmp_path: Path, manifest: dict) -> Path:
    """Materialise a synthetic manifest plus the source files it references."""
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    for section, entries in manifest.items():
        if section == "version":
            continue
        for entry in entries:
            source = tmp_path / "templates" / "consumer-repo" / entry["source"]
            if entry.get("is_directory"):
                source.mkdir(parents=True, exist_ok=True)
                (source / "index.js").write_text("// fixture\n", encoding="utf-8")
            else:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("# fixture\n", encoding="utf-8")
    path = tmp_path / ".github" / "sync-manifest.yml"
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return path


def write_sync_workflow(tmp_path: Path, repos: list[str]) -> Path:
    path = tmp_path / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    listing = "\n".join(f"    {repo}" for repo in repos)
    path.write_text(f"env:\n  REGISTERED_CONSUMER_REPOS: |\n{listing}\n", encoding="utf-8")
    return path


def synthetic_preset(tmp_path: Path, manifest: dict, repos: list[str]) -> dict:
    return build_preset(
        manifest=write_manifest(tmp_path, manifest),
        sync_workflow=write_sync_workflow(tmp_path, repos),
        repo_root=tmp_path,
    )


# --------------------------------------------------------------------------
# Live-manifest contract
# --------------------------------------------------------------------------


def test_manifest_managed_workflows_are_disabled_for_consumers():
    """Deliberate-break gate for issue #2876.

    Remove the agents-guard.yml entry from .github/sync-manifest.yml (or hand-edit
    the generated rule) and this test must fail.
    """
    preset = committed_preset()
    consumers = [repo for repo in registered_consumers() if repo != SOURCE_REPO]
    assert consumers, "no registered consumer repos parsed from maint-68"

    for repo in consumers:
        effective = disabled_paths(preset, repo)
        for path in INCIDENT_PATHS:
            assert path in effective, f"{path} must be invisible to Renovate in {repo}"
        assert effective == expected_managed(repo), (
            f"{repo}: preset disagrees with the live manifest. Run "
            "`python scripts/generate_consumer_renovate_ownership.py`."
        )


def test_create_only_targets_stay_visible_to_consumer_renovate():
    """`.github/workflows/ci.yml` is create_only, so consumers own their copy."""
    preset = committed_preset()
    consumers = [
        repo for repo in registered_consumers() if repo not in {SOURCE_REPO, "stranske/Template"}
    ]

    for repo in consumers:
        effective = disabled_paths(preset, repo)
        assert ".github/workflows/ci.yml" not in effective
        assert ".github/workflows/pr-00-gate.yml" not in effective
        assert ".github/renovate.json" not in effective


def test_overwrite_repos_opt_back_into_managed_paths():
    """stranske/Template is in ci.yml's overwrite_repos, so it is managed there."""
    effective = disabled_paths(committed_preset(), "stranske/Template")
    assert ".github/workflows/ci.yml" in effective
    assert ".github/workflows/pr-00-gate.yml" in effective


def test_skip_repos_keep_the_path_consumer_owned():
    """AGENTS.md is skipped for Trend_Model_Project but managed elsewhere."""
    preset = committed_preset()
    assert "AGENTS.md" not in disabled_paths(preset, "stranske/Trend_Model_Project")
    assert "AGENTS.md" in disabled_paths(preset, "stranske/Inv-Man-Intake")

    # trip-planner skips the vendored npm cascade; everyone else receives it.
    assert ".github/scripts/package.json" not in disabled_paths(preset, "stranske/trip-planner")
    assert ".github/scripts/package.json" in disabled_paths(preset, "stranske/Inv-Man-Intake")


def test_directory_entries_use_a_recursive_glob():
    effective = disabled_paths(committed_preset(), "stranske/Inv-Man-Intake")
    assert ".github/scripts/node_modules/minimatch/**" in effective
    assert "scripts/runner_lib/**" in effective


def test_source_repository_is_never_matched():
    """Workflows is the sync source; its canonical files stay Renovate-managed."""
    preset = committed_preset()
    for rule in preset["packageRules"]:
        assert SOURCE_REPO not in rule["matchRepositories"]
    assert disabled_paths(preset, SOURCE_REPO) == set()


def test_preset_does_not_blanket_ignore_workflows():
    """Non-goal: never disable all of `.github/workflows/**`."""
    for rule in committed_preset()["packageRules"]:
        for pattern in rule["matchFileNames"]:
            assert pattern not in {".github/workflows/**", ".github/**", "**"}


def test_fleet_preset_extends_the_generated_ownership_preset():
    fleet = json.loads(FLEET_PRESET.read_text(encoding="utf-8"))
    assert "github>stranske/Workflows//renovate-presets/consumer-managed-paths" in fleet["extends"]


def test_committed_preset_is_not_stale():
    expected = render(build_preset(manifest=MANIFEST, sync_workflow=SYNC_WORKFLOW, repo_root=ROOT))
    assert PRESET.read_text(encoding="utf-8") == expected


def test_check_mode_reports_drift(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert main(["--check"]) == 0

    stale = tmp_path / "stale.json"
    stale.write_text('{"packageRules": []}\n', encoding="utf-8")
    assert main(["--check", "--output", str(stale)]) == 1
    assert "is stale" in capsys.readouterr().err


def test_generator_writes_the_output_file(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    out = tmp_path / "nested" / "preset.json"
    assert main(["--output", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["packageRules"]


# --------------------------------------------------------------------------
# Synthetic-manifest unit coverage
# --------------------------------------------------------------------------


@pytest.fixture
def repos() -> list[str]:
    return ["stranske/Alpha", "stranske/Beta"]


def test_exact_file_entry_is_managed_everywhere(tmp_path, repos):
    manifest = {
        "version": 1,
        "workflows": [{"source": ".github/workflows/managed.yml", "description": "managed"}],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    for repo in repos:
        assert disabled_paths(preset, repo) == {".github/workflows/managed.yml"}


def test_directory_entry_expands_to_recursive_glob(tmp_path, repos):
    manifest = {
        "version": 1,
        "scripts": [
            {
                "source": ".github/scripts/vendored",
                "description": "vendored directory",
                "is_directory": True,
            }
        ],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    assert disabled_paths(preset, "stranske/Alpha") == {".github/scripts/vendored/**"}


def test_create_only_entry_is_not_managed(tmp_path, repos):
    manifest = {
        "version": 1,
        "workflows": [
            {
                "source": ".github/workflows/seeded.yml",
                "description": "seeded once",
                "sync_mode": "create_only",
            }
        ],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    assert preset["packageRules"] == []


def test_overwrite_repos_reinstates_create_only_management(tmp_path, repos):
    manifest = {
        "version": 1,
        "workflows": [
            {
                "source": ".github/workflows/seeded.yml",
                "description": "seeded once",
                "sync_mode": "create_only",
                "overwrite_repos": ["stranske/Beta"],
            }
        ],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    assert disabled_paths(preset, "stranske/Alpha") == set()
    assert disabled_paths(preset, "stranske/Beta") == {".github/workflows/seeded.yml"}


def test_skip_repos_excludes_only_the_named_repo(tmp_path, repos):
    manifest = {
        "version": 1,
        "workflows": [
            {
                "source": ".github/workflows/managed.yml",
                "description": "managed",
                "skip_repos": [{"repo": "stranske/Alpha", "reason": "custom"}],
            }
        ],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    assert disabled_paths(preset, "stranske/Alpha") == set()
    assert disabled_paths(preset, "stranske/Beta") == {".github/workflows/managed.yml"}


def test_target_override_is_used_instead_of_source(tmp_path, repos):
    manifest = {
        "version": 1,
        "scripts": [
            {
                "source": "scripts/helper.py",
                "target": "tools/helper.py",
                "description": "retargeted",
            }
        ],
    }
    preset = synthetic_preset(tmp_path, manifest, repos)
    assert disabled_paths(preset, "stranske/Alpha") == {"tools/helper.py"}


def test_generation_is_deterministic(tmp_path, repos):
    manifest = {
        "version": 1,
        "workflows": [
            {"source": ".github/workflows/b.yml", "description": "b"},
            {"source": ".github/workflows/a.yml", "description": "a"},
        ],
    }
    first = render(synthetic_preset(tmp_path / "one", manifest, repos))
    second = render(synthetic_preset(tmp_path / "two", manifest, list(reversed(repos))))
    assert first == second
