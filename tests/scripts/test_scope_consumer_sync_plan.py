from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.scope_consumer_sync_plan import (
    PlanScopeError,
    changed_paths_for_range,
    select_plan,
)


def entry(
    source: str,
    target: str,
    *,
    directory: bool = False,
    requires: list[str] | None = None,
) -> dict[str, object]:
    return {
        "section": "workflows",
        "source": target,
        "resolved_source": source,
        "target": target,
        "description": target,
        "sync_mode": None,
        "is_directory": directory,
        "skip_repos": [],
        "skip_reasons": {},
        "overwrite_repos": [],
        "template_sync": None,
        "delivery": "copy",
        "requires": requires or [],
        "content_sha256": "sha256:" + "1" * 64,
        "effect_fingerprint": "sha256:" + "2" * 64,
    }


def plan() -> dict[str, object]:
    return {
        "schema": "workflows.consumer-sync-plan/v1",
        "version": 1,
        "plan_id": "sha256:" + "a" * 64,
        "manifest_sha256": "sha256:" + "b" * 64,
        "entries": [
            entry(
                "templates/consumer-repo/.github/workflows/autofix.yml",
                ".github/workflows/autofix.yml",
            ),
            entry(".github/scripts/runner", ".github/scripts/runner", directory=True),
            entry("templates/consumer-repo/AGENTS.md", "AGENTS.md"),
        ],
        "removals": [
            {
                "target": ".github/workflows/legacy.yml",
                "description": "legacy",
                "effect_fingerprint": "sha256:" + "3" * 64,
            }
        ],
    }


def test_source_delta_selects_only_changed_manifest_sources() -> None:
    scoped, evidence = select_plan(
        plan(),
        mode="source-delta",
        changed_paths=[
            "templates/consumer-repo/.github/workflows/autofix.yml",
            ".github/scripts/runner/lib.js",
            "README.md",
        ],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )

    assert [item["target"] for item in scoped["entries"]] == [
        ".github/workflows/autofix.yml",
        ".github/scripts/runner",
    ]
    assert scoped["removals"] == []
    assert scoped["plan_id"] != plan()["plan_id"]
    assert evidence["ignored_changed_paths"] == ["README.md"]
    assert evidence["selected_entry_count"] == 2
    assert evidence["source_commit"] == "2" * 40


def test_source_delta_carries_path_classifier_delivery_contract() -> None:
    scoped_plan = plan()
    scoped_plan["entries"].extend(
        [
            entry(
                "templates/consumer-repo/.github/actions/path-classifier",
                ".github/actions/path-classifier",
                directory=True,
                requires=[".github/scripts/sync_pr_lease_contract.js"],
            ),
            entry(
                ".github/scripts/sync_pr_lease_contract.js",
                ".github/scripts/sync_pr_lease_contract.js",
            ),
        ]
    )

    scoped, evidence = select_plan(
        scoped_plan,
        mode="source-delta",
        changed_paths=["templates/consumer-repo/.github/actions/path-classifier/classify.js"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )

    assert [item["target"] for item in scoped["entries"]] == [
        ".github/actions/path-classifier",
        ".github/scripts/sync_pr_lease_contract.js",
    ]
    assert evidence["dependency_targets"] == [".github/scripts/sync_pr_lease_contract.js"]


def test_source_delta_expands_transitive_manifest_dependencies() -> None:
    scoped_plan = plan()
    scoped_plan["entries"].extend(
        [
            entry("scripts/a", "scripts/a", requires=["scripts/b"]),
            entry("scripts/b", "scripts/b", requires=["scripts/c"]),
            entry("scripts/c", "scripts/c"),
        ]
    )
    scoped, evidence = select_plan(
        scoped_plan,
        mode="source-delta",
        changed_paths=["scripts/a"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )
    assert [item["target"] for item in scoped["entries"]][-3:] == [
        "scripts/a",
        "scripts/b",
        "scripts/c",
    ]
    assert evidence["dependency_targets"] == ["scripts/b", "scripts/c"]


def test_source_delta_dependency_cycle_terminates() -> None:
    scoped_plan = plan()
    scoped_plan["entries"].extend(
        [
            entry("scripts/x", "scripts/x", requires=["scripts/y"]),
            entry("scripts/y", "scripts/y", requires=["scripts/x"]),
        ]
    )
    scoped, evidence = select_plan(
        scoped_plan,
        mode="source-delta",
        changed_paths=["scripts/x"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )
    assert [item["target"] for item in scoped["entries"]][-2:] == [
        "scripts/x",
        "scripts/y",
    ]
    assert evidence["dependency_targets"] == ["scripts/y"]


def test_full_scope_preserves_the_compiled_plan_exactly() -> None:
    original = plan()
    scoped, evidence = select_plan(original, mode="full", source_commit="2" * 40)

    assert scoped == original
    assert evidence["full_plan_id"] == evidence["plan_id"] == original["plan_id"]
    assert evidence["selected_removal_count"] == 1


def test_manifest_change_requires_full_scope() -> None:
    with pytest.raises(PlanScopeError, match="manifest_change_requires_full_scope"):
        select_plan(
            plan(),
            mode="source-delta",
            changed_paths=[".github/sync-manifest.yml"],
            base_sha="1" * 40,
            source_commit="2" * 40,
        )


def test_cli_uses_exact_git_range_and_emits_scope_outputs(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "templates/consumer-repo/.github/workflows/autofix.yml"
    source.parent.mkdir(parents=True)
    source.write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    source.write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "update"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan()), encoding="utf-8")
    output = tmp_path / "scoped.json"
    evidence = tmp_path / "scope.json"
    github_output = tmp_path / "github-output"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts/scope_consumer_sync_plan.py"),
            "--plan",
            str(plan_path),
            "--mode",
            "source-delta",
            "--base-ref",
            base,
            "--head-ref",
            head,
            "--repo-root",
            str(tmp_path),
            "--output-json",
            str(output),
            "--scope-evidence-json",
            str(evidence),
            "--github-output",
            str(github_output),
        ],
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["entries"][0]["target"] == (
        ".github/workflows/autofix.yml"
    )
    scope = json.loads(evidence.read_text(encoding="utf-8"))
    assert scope["base_sha"] == base
    assert scope["source_commit"] == head
    outputs = github_output.read_text(encoding="utf-8")
    assert "plan_scope=source-delta" in outputs
    assert "has_plan_items=true" in outputs
    assert f"scope_base_sha={base}" in outputs
    assert f"source_commit={head}" in outputs


def test_cli_emits_false_when_source_delta_has_no_plan_items(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    readme = tmp_path / "README.md"
    readme.write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    readme.write_text("new\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "unmanaged update"], cwd=tmp_path, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan()), encoding="utf-8")
    output = tmp_path / "scoped.json"
    github_output = tmp_path / "github-output"

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[2] / "scripts/scope_consumer_sync_plan.py"),
            "--plan",
            str(plan_path),
            "--mode",
            "source-delta",
            "--base-ref",
            base,
            "--head-ref",
            head,
            "--repo-root",
            str(tmp_path),
            "--output-json",
            str(output),
            "--scope-evidence-json",
            str(tmp_path / "scope.json"),
            "--github-output",
            str(github_output),
        ],
        cwd=Path(__file__).parents[2],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    scoped = json.loads(output.read_text(encoding="utf-8"))
    assert scoped["entries"] == []
    assert scoped["removals"] == []
    assert "has_plan_items=false" in github_output.read_text(encoding="utf-8")


def test_git_range_rejects_a_base_from_a_divergent_branch(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "managed.txt"
    source.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    common = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    subprocess.run(["git", "checkout", "-qb", "left"], cwd=tmp_path, check=True)
    source.write_text("left\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "left"], cwd=tmp_path, check=True)
    left = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-qb", "right", common], cwd=tmp_path, check=True)
    source.write_text("right\n", encoding="utf-8")
    subprocess.run(["git", "commit", "-qam", "right"], cwd=tmp_path, check=True)
    right = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()

    with pytest.raises(PlanScopeError, match="scope_base_is_not_ancestor_of_source_commit"):
        changed_paths_for_range(tmp_path, left, right)
