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
from scripts.sync_manifest_compiler import compile_manifest


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


def test_real_validator_delta_includes_all_registered_schema_dependencies() -> None:
    root = Path(__file__).resolve().parents[2]
    full_plan = compile_manifest(root / ".github/sync-manifest.yml").to_plan()
    scoped, evidence = select_plan(
        full_plan,
        mode="source-delta",
        changed_paths=["scripts/validate_run_contract.py"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )
    targets = {item["target"] for item in scoped["entries"]}
    assert "scripts/validate_run_contract.py" in targets
    assert {
        f"docs/contracts/schemas/{name}-v1.schema.json"
        for name in (
            "run-contract",
            "artifact-manifest",
            "tracked-variable",
            "capability-bundle",
            "mosaic-core",
            "document-mirror",
            "output-substrate",
        )
    } <= targets
    assert "docs/contracts/schemas/evidence-object-v1.schema.json" in targets
    assert "docs/contracts/schemas/mosaic-core-v1.schema.json" in evidence["dependency_targets"]
    assert "docs/contracts/identity-map-conventions.md" not in targets


def test_evidence_schema_delta_includes_scoped_packaged_consumer_targets() -> None:
    root = Path(__file__).resolve().parents[2]
    full_plan = compile_manifest(root / ".github/sync-manifest.yml").to_plan()
    scoped, _ = select_plan(
        full_plan,
        mode="source-delta",
        changed_paths=["docs/contracts/schemas/evidence-object-v1.schema.json"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )
    package_entries = {
        (entry["target"], tuple(entry["include_repos"]))
        for entry in scoped["entries"]
        if entry["target"].endswith("/evidence-object-v1.schema.json")
        and entry["target"] != "docs/contracts/schemas/evidence-object-v1.schema.json"
    }
    assert package_entries == {
        (
            "src/deliverable_render/store/evidence-object-v1.schema.json",
            ("stranske/Deliverable-Render",),
        ),
        ("src/manager_mosaic/schemas/evidence-object-v1.schema.json", ("stranske/Manager-Mosaic",)),
    }


@pytest.mark.parametrize(
    ("document", "schemas"),
    [
        (
            "mosaic-core",
            {"mosaic-core-v1.schema.json", "artifact-manifest-v1.schema.json"},
        ),
        ("document-mirror", {"document-mirror-v1.schema.json"}),
        (
            "output-substrate",
            {"output-substrate-v1.schema.json", "artifact-manifest-v1.schema.json"},
        ),
    ],
)
def test_real_contract_doc_delta_carries_its_schemas(document: str, schemas: set[str]) -> None:
    root = Path(__file__).resolve().parents[2]
    full_plan = compile_manifest(root / ".github/sync-manifest.yml").to_plan()
    scoped, _ = select_plan(
        full_plan,
        mode="source-delta",
        changed_paths=[f"docs/contracts/{document}-v1.md"],
        base_sha="1" * 40,
        source_commit="2" * 40,
    )
    targets = {item["target"] for item in scoped["entries"]}
    assert {f"docs/contracts/schemas/{schema}" for schema in schemas} <= targets


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


@pytest.mark.parametrize(
    "changed_path",
    [
        "scripts/sync_status_file_ignores.py",
        "templates/consumer-repo/.gitignore",
        "templates/consumer-repo/scripts/sync_status_file_ignores.py",
    ],
)
def test_status_ignore_change_requires_full_scope(changed_path: str) -> None:
    with pytest.raises(PlanScopeError, match="status_ignore_change_requires_full_scope"):
        select_plan(
            plan(),
            mode="source-delta",
            changed_paths=[changed_path],
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


def _commit_fixture(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


@pytest.fixture
def metadata_range(tmp_path: Path):
    import yaml

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    manifest = tmp_path / ".github/sync-manifest.yml"
    manifest.parent.mkdir()
    document = {
        "version": 1,
        "scripts": [
            {"source": "scripts/parser.py", "description": "old parser"},
            {"source": "scripts/vendor", "description": "vendored helper", "is_directory": True},
        ],
        "workflows": [
            {
                "source": ".github/workflows/pr-00-gate.yml",
                "description": "gate",
                "sync_mode": "create_only",
                "overwrite_repos": ["stranske/Template"],
            }
        ],
        "removals": [{"target": ".github/workflows/legacy.yml", "description": "historic removal"}],
        "excluded": [{"source": "not-delivered", "reason": "unchanged"}],
    }
    parser = tmp_path / "scripts/parser.py"
    parser.parent.mkdir()
    parser.write_text("old parser\n")
    vendor = tmp_path / "scripts/vendor"
    vendor.mkdir()
    (vendor / "helper.js").write_text("unchanged tracked helper")
    (tmp_path / ".gitignore").write_text("scripts/vendor/*.log\n")
    gate = tmp_path / "templates/consumer-repo/.github/workflows/pr-00-gate.yml"
    gate.parent.mkdir(parents=True)
    gate.write_text("unchanged protected gate\n")
    manifest.write_text(yaml.safe_dump(document, sort_keys=False))
    base = _commit_fixture(tmp_path, "base")
    return tmp_path, manifest, document, parser, base


def _finish_metadata_range(fixture, mutate=None):
    import yaml

    root, manifest, document, parser, base = fixture
    document["scripts"][0]["description"] = "new parser description"
    if mutate:
        mutate(document)
    manifest.write_text(yaml.safe_dump(document, sort_keys=False) + "# description-only comment\n")
    parser.write_text("reviewed new parser\n")
    head = _commit_fixture(root, "source repair and metadata")
    return root, base, head


def _select_actual(root, base, head, full=None):
    actual_base, actual_head, paths = changed_paths_for_range(root, base, head)
    if full is None:
        full = compile_manifest(root / ".github/sync-manifest.yml").to_plan()
    return select_plan(
        full,
        mode="source-delta",
        changed_paths=paths,
        base_sha=actual_base,
        source_commit=actual_head,
        repo_root=root,
    )


def test_description_only_range_selects_one_payload_without_gate_or_historic_removal(
    metadata_range,
):
    root, base, head = _finish_metadata_range(metadata_range)
    scoped, evidence = _select_actual(root, base, head)
    assert [row["target"] for row in scoped["entries"]] == ["scripts/parser.py"]
    assert scoped["removals"] == []
    assert evidence["selected_entry_count"] == 1
    assert evidence["selected_removal_count"] == 0
    assert evidence["ignored_changed_paths"] == [".github/sync-manifest.yml"]
    proof = evidence["manifest_selector_equivalence"]
    assert proof["base_sha"] == base and proof["source_commit"] == head
    assert proof["allowed_difference"] == "known_descriptions_and_comments_only"
    assert proof["base_manifest_sha256"] != proof["source_manifest_sha256"]
    assert subprocess.check_output(
        ["git", "ls-tree", head, "scripts/parser.py"], cwd=root, text=True
    ).startswith("100644 blob ")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["scripts"][0].update(target="other.py"),
        lambda d: d["scripts"][0].update(source="scripts/other.py"),
        lambda d: d["scripts"][0].update(source_tree="template"),
        lambda d: d["scripts"][0].update(sync_mode="create_only"),
        lambda d: d["workflows"][0].pop("sync_mode"),
        lambda d: d["workflows"][0].update(overwrite_repos=[]),
        lambda d: d["scripts"][0].update(include_repos=["stranske/Template"]),
        lambda d: d["scripts"][0].update(skip_repos=["stranske/Other"]),
        lambda d: d["scripts"][0].update(requires=[".github/workflows/pr-00-gate.yml"]),
        lambda d: d["scripts"][0].update(is_directory=True),
        lambda d: d["scripts"][0].update(template_sync="exact"),
        lambda d: d["scripts"][0].update(delivery="runtime"),
        lambda d: d["scripts"][0].update(unknown_selector=True),
        lambda d: d.update(unknown_section=[]),
        lambda d: d["scripts"][0].update(mode="100755"),
        lambda d: d["scripts"][0].update(description={"unknown": "not operator text"}),
        lambda d: d["removals"].append({"target": "delete-me", "description": "new removal"}),
        lambda d: d["removals"].clear(),
        lambda d: d["removals"][0].update(target="different-delete"),
        lambda d: d["excluded"][0].update(reason="changed ignored policy"),
        lambda d: d.update(version=True),
    ],
)
def test_operational_or_unknown_manifest_changes_keep_full_scope_refusal(metadata_range, mutation):
    # Build the supplied plan before the malicious/operational range. The new
    # gate must reject invalid manifests as well as valid selector changes.
    root, manifest, _, _, _ = metadata_range
    full = compile_manifest(manifest).to_plan()
    root, base, head = _finish_metadata_range(metadata_range, mutation)
    with pytest.raises(PlanScopeError, match="manifest_change_requires_full_scope"):
        _select_actual(root, base, head, full)


def test_description_changes_on_removal_cannot_replay_historic_delete(metadata_range):
    root, base, head = _finish_metadata_range(
        metadata_range,
        lambda d: d["removals"][0].update(description="clearer historical rationale"),
    )
    scoped, _ = _select_actual(root, base, head)
    assert scoped["removals"] == []


@pytest.mark.parametrize(
    "tamper",
    [
        "plan_content",
        "plan_mode",
        "source_content",
        "checkout",
        "duplicate_yaml",
        "alias_yaml",
        "recompiled_dirty_source",
        "source_mode",
        "different_head",
        "manifest_mode",
        "untracked_child",
        "ignored_child",
        "assume_unchanged",
        "hidden_mode",
    ],
)
def test_manifest_equivalence_cannot_use_stale_or_ambiguous_evidence(metadata_range, tamper):
    root, manifest, _, parser, _ = metadata_range
    root, base, head = _finish_metadata_range(metadata_range)
    full = compile_manifest(manifest).to_plan()
    if tamper == "plan_content":
        full["entries"][0]["content_sha256"] = "sha256:" + "f" * 64
    elif tamper == "plan_mode":
        full["entries"][0]["sync_mode"] = None
    elif tamper == "source_content":
        parser.write_text("uncompiled source mutation")
    elif tamper == "checkout":
        manifest.write_text(manifest.read_text() + "# uncommitted change\n")
    elif tamper == "recompiled_dirty_source":
        parser.write_text("dirty payload compiled into a self-consistent plan")
        full = compile_manifest(manifest).to_plan()
    elif tamper == "source_mode":
        parser.chmod(0o755)
        full = compile_manifest(manifest).to_plan()
    elif tamper == "different_head":
        parser.write_text("later committed payload")
        _commit_fixture(root, "different source identity")
        full = compile_manifest(manifest).to_plan()
    elif tamper == "manifest_mode":
        manifest.chmod(0o755)
        head = _commit_fixture(root, "manifest mode changed")
        full = compile_manifest(manifest).to_plan()
    elif tamper in {"untracked_child", "ignored_child"}:
        suffix = "cache.log" if tamper == "ignored_child" else "unexpected.js"
        (root / "scripts/vendor" / suffix).write_text("not in immutable Git payload")
        full = compile_manifest(manifest).to_plan()
    elif tamper == "assume_unchanged":
        subprocess.run(
            ["git", "update-index", "--assume-unchanged", "scripts/parser.py"], cwd=root, check=True
        )
        parser.write_text("hidden dirty parser")
        full = compile_manifest(manifest).to_plan()
    elif tamper == "hidden_mode":
        subprocess.run(["git", "config", "core.filemode", "false"], cwd=root, check=True)
        parser.chmod(0o755)
        full = compile_manifest(manifest).to_plan()
    else:
        suffix = "\nversion: 1\n" if tamper == "duplicate_yaml" else "\nignored: &x [*x]\n"
        manifest.write_text(manifest.read_text() + suffix)
        head = _commit_fixture(root, "ambiguous manifest")
    with pytest.raises(PlanScopeError, match="manifest_change_requires_full_scope"):
        _select_actual(root, base, head, full)


def test_manifest_metadata_cannot_admit_a_deleted_empty_source_directory(metadata_range):
    root, manifest, _, _, _ = metadata_range
    root, base, _ = _finish_metadata_range(metadata_range)
    subprocess.run(["git", "rm", "-q", "scripts/vendor/helper.js"], cwd=root, check=True)
    head = _commit_fixture(root, "delete last tracked source member")
    (root / "scripts/vendor").mkdir(exist_ok=True)
    full = compile_manifest(manifest).to_plan()
    with pytest.raises(PlanScopeError, match="manifest_change_requires_full_scope"):
        _select_actual(root, base, head, full)
