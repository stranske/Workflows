from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from scripts.sync_manifest_compiler import (
    PLAN_SCHEMA,
    ManifestCompileError,
    compile_manifest,
    resolve_source_path,
)


def write_manifest(root: Path, text: str) -> Path:
    path = root / ".github" / "sync-manifest.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_source(root: Path, source: str, *, template: bool, content: str = "content\n") -> Path:
    base = root / "templates" / "consumer-repo" if template else root
    path = base / source
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_template_owned_entry_compiles_to_typed_plan(tmp_path: Path) -> None:
    write_source(tmp_path, ".github/workflows/autofix.yml", template=True)
    manifest = write_manifest(
        tmp_path,
        """version: 1
workflows:
  - source: .github/workflows/autofix.yml
    description: Autofix
""",
    )

    compiled = compile_manifest(manifest)
    entry = compiled.section("workflows")[0]
    plan = compiled.to_plan()

    assert entry.resolved_source == ("templates/consumer-repo/.github/workflows/autofix.yml")
    assert entry.target == entry.source
    assert entry.delivery == "copy"
    assert entry.content_sha256.startswith("sha256:")
    assert entry.effect_fingerprint.startswith("sha256:")
    assert plan["schema"] == PLAN_SCHEMA
    assert plan["plan_id"].startswith("sha256:")


def test_root_owned_entry_uses_documented_precedence(tmp_path: Path) -> None:
    root_source = write_source(tmp_path, "scripts/tool.py", template=False, content="root\n")
    write_source(tmp_path, "scripts/tool.py", template=True, content="template\n")
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/tool.py
    target: scripts/renamed.py
    description: Tool
    delivery: copy
""",
    )

    entry = compile_manifest(manifest).section("scripts")[0]

    assert entry.resolved_source == "scripts/tool.py"
    assert entry.target == "scripts/renamed.py"
    assert entry.content_sha256.endswith(
        __import__("hashlib").sha256(root_source.read_bytes()).hexdigest()
    )


def test_template_owned_entry_prefers_template_when_both_exist(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, ".github/workflows/ci.yml", template=False, content="root\n")
    write_source(
        tmp_path,
        ".github/workflows/ci.yml",
        template=True,
        content="template\n",
    )
    manifest = write_manifest(
        tmp_path,
        """version: 1
workflows:
  - source: .github/workflows/ci.yml
    description: CI
""",
    )

    entry = compile_manifest(manifest).section("workflows")[0]
    assert entry.resolved_source.startswith("templates/consumer-repo/")


def test_missing_source_fails_before_plan_emission(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        """version: 1
workflows:
  - source: .github/workflows/missing.yml
    description: Missing
""",
    )

    with pytest.raises(ManifestCompileError, match="not deliverable"):
        compile_manifest(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source", "../secret"),
        ("source", "/absolute"),
        ("source", "a/./b"),
        ("source", "..\\\\secret"),
        ("target", "../../escape"),
        ("target", "./ambiguous"),
        ("target", "."),
    ],
)
def test_unsafe_paths_are_rejected(tmp_path: Path, field: str, value: str) -> None:
    source = "scripts/tool.py"
    write_source(tmp_path, source, template=False)
    target_line = f"    target: {value}\n" if field == "target" else ""
    source_value = value if field == "source" else source
    manifest = write_manifest(
        tmp_path,
        "version: 1\nscripts:\n"
        f"  - source: {source_value}\n"
        f"{target_line}"
        "    description: Tool\n",
    )

    with pytest.raises(ManifestCompileError, match="safe repository-relative"):
        compile_manifest(manifest)


@pytest.mark.parametrize("yaml_value", ["123", "null", "false"])
def test_non_string_paths_are_rejected(tmp_path: Path, yaml_value: str) -> None:
    write_source(tmp_path, "scripts/tool.py", template=False)
    manifest = write_manifest(
        tmp_path,
        "version: 1\nscripts:\n" f"  - source: {yaml_value}\n" "    description: Tool\n",
    )

    with pytest.raises(ManifestCompileError, match="safe repository-relative"):
        compile_manifest(manifest)


def test_resolver_preserves_legacy_fallback_and_rejects_unsafe_paths(tmp_path: Path) -> None:
    root_file = write_source(tmp_path, "docs/contract.md", template=False)
    assert resolve_source_path("docs/contract.md", None, repo_root=tmp_path) == root_file
    assert resolve_source_path("../outside", None, repo_root=tmp_path) is None
    assert resolve_source_path("/etc/passwd", None, repo_root=tmp_path) is None


def test_sources_escaping_via_symlink_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-source.txt"
    outside.write_text("outside\n", encoding="utf-8")
    symlink = tmp_path / "scripts" / "outside.py"
    symlink.parent.mkdir(parents=True)
    symlink.symlink_to(outside)
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/outside.py
    description: Outside
""",
    )

    with pytest.raises(ManifestCompileError, match="escapes repository root"):
        compile_manifest(manifest)


def test_directories_with_escaping_symlinks_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-child.txt"
    outside.write_text("outside\n", encoding="utf-8")
    directory = tmp_path / "scripts" / "bundle"
    directory.mkdir(parents=True)
    (directory / "safe.py").write_text("safe\n", encoding="utf-8")
    (directory / "outside.py").symlink_to(outside)
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/bundle
    description: Bundle
    is_directory: true
""",
    )

    with pytest.raises(ManifestCompileError, match="invalid symlink"):
        compile_manifest(manifest)


def test_directories_with_cyclic_symlinks_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "scripts" / "bundle"
    directory.mkdir(parents=True)
    (directory / "safe.py").write_text("safe\n", encoding="utf-8")
    (directory / "first").symlink_to(directory / "second")
    (directory / "second").symlink_to(directory / "first")
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/bundle
    description: Bundle
    is_directory: true
""",
    )

    with pytest.raises(ManifestCompileError, match="invalid symlink"):
        compile_manifest(manifest)


def test_duplicate_copy_and_removal_targets_are_rejected(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "scripts/a.py", template=False)
    write_source(tmp_path, "scripts/b.py", template=False)
    duplicate_copy = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/a.py
    target: scripts/same.py
    description: A
  - source: scripts/b.py
    target: scripts/same.py
    description: B
""",
    )
    with pytest.raises(ManifestCompileError, match="duplicate effective target"):
        compile_manifest(duplicate_copy)

    duplicate_removal = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/a.py
    target: scripts/a.py
    description: A
removals:
  - target: scripts/a.py
    description: Remove A
""",
    )
    with pytest.raises(ManifestCompileError, match="duplicate effective target"):
        compile_manifest(duplicate_removal)


def test_manifest_requires_are_typed_and_fail_closed(tmp_path: Path) -> None:
    write_source(tmp_path, "scripts/a.py", template=False)
    write_source(tmp_path, "scripts/b.py", template=False)
    valid = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/a.py
    description: A
    requires:
      - scripts/b.py
  - source: scripts/b.py
    description: B
""",
    )
    plan = compile_manifest(valid).to_plan()
    assert plan["entries"][0]["requires"] == ["scripts/b.py"]

    unknown = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/a.py
    description: A
    requires:
      - scripts/missing.py
""",
    )
    with pytest.raises(ManifestCompileError, match="requires unknown manifest target"):
        compile_manifest(unknown)

    cycle = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/a.py
    description: A
    requires: [scripts/b.py]
  - source: scripts/b.py
    description: B
    requires: [scripts/a.py]
""",
    )
    with pytest.raises(ManifestCompileError, match="manifest requires cycle"):
        compile_manifest(cycle)


def test_directory_hash_and_plan_are_deterministic(tmp_path: Path) -> None:
    directory = tmp_path / "scripts" / "runner_lib"
    directory.mkdir(parents=True)
    (directory / "b.py").write_text("b\n", encoding="utf-8")
    (directory / "a.py").write_text("a\n", encoding="utf-8")
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/runner_lib
    description: Runner library
    is_directory: true
""",
    )

    first = compile_manifest(manifest).to_plan()
    second = compile_manifest(manifest).to_plan()

    assert first == second
    assert first["entries"][0]["is_directory"] is True
    assert first["entries"][0]["content_sha256"].startswith("sha256:")


def test_skip_overwrite_template_sync_and_removal_are_normalized(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "tools/requirements.txt", template=False)
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: tools/requirements.txt
    description: Requirements
    sync_mode: create_only
    template_sync: exact
    skip_repos:
      - repo: owner/skipped
        reason: Intentional exception
    overwrite_repos:
      - owner/template
removals:
  - target: obsolete.txt
    description: Obsolete
""",
    )

    plan = compile_manifest(manifest).to_plan()
    entry = plan["entries"][0]

    assert entry["sync_mode"] == "create_only"
    assert entry["template_sync"] == "exact"
    assert entry["skip_repos"] == ["owner/skipped"]
    assert entry["skip_reasons"] == {"owner/skipped": "Intentional exception"}
    assert entry["overwrite_repos"] == ["owner/template"]
    assert plan["removals"][0]["effect_fingerprint"].startswith("sha256:")


@pytest.mark.parametrize(
    "fragment",
    [
        "sync_mode: overwrite",
        "template_sync: loose",
        "delivery: runtime",
        "overwrite_repos: owner/repo",
        "skip_repos: owner/repo",
        "is_directory: 'yes'",
    ],
)
def test_invalid_typed_fields_fail_closed(tmp_path: Path, fragment: str) -> None:
    write_source(tmp_path, "scripts/tool.py", template=False)
    manifest = write_manifest(
        tmp_path,
        "version: 1\nscripts:\n"
        "  - source: scripts/tool.py\n"
        "    description: Tool\n"
        f"    {fragment}\n",
    )
    with pytest.raises(ManifestCompileError):
        compile_manifest(manifest)


def test_cli_emits_deterministic_json_and_github_outputs(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "scripts/tool.py", template=False)
    manifest = write_manifest(
        tmp_path,
        """version: 1
scripts:
  - source: scripts/tool.py
    description: Tool
""",
    )
    output = tmp_path / "plan.json"
    github_output = tmp_path / "github-output"
    command = [
        sys.executable,
        "scripts/sync_manifest_compiler.py",
        "--manifest",
        str(manifest),
        "--output-json",
        str(output),
        "--github-output",
        str(github_output),
    ]

    first = subprocess.run(command, capture_output=True, text=True)
    first_bytes = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True)

    assert first.returncode == second.returncode == 0
    assert output.read_bytes() == first_bytes
    assert json.loads(output.read_text())["schema"] == PLAN_SCHEMA
    outputs = github_output.read_text(encoding="utf-8")
    assert "plan_id=sha256:" in outputs
    assert "template_hash=" in outputs


def test_real_manifest_compiles_every_declared_copy_entry() -> None:
    root = Path(__file__).parents[2]
    compiled = compile_manifest(root / ".github" / "sync-manifest.yml", repo_root=root)
    plan = compiled.to_plan()
    schema = json.loads(
        (root / "docs" / "contracts" / "schemas" / "consumer-sync-plan-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert plan["schema"] == PLAN_SCHEMA
    Draft202012Validator(schema).validate(plan)
    assert len(plan["entries"]) > 200
    assert all(entry["resolved_source"] for entry in plan["entries"])
    assert len({entry["target"] for entry in plan["entries"]}) == len(plan["entries"])


def test_maint_sync_consumes_compiled_plan_for_paths_and_hash() -> None:
    root = Path(__file__).parents[2]
    workflow = (root / ".github" / "workflows" / "maint-68-sync-consumer-repos.yml").read_text(
        encoding="utf-8"
    )

    assert "--output-json manifest.json" in workflow
    assert "steps.manifest.outputs.template_hash" in workflow
    assert "item['resolved_source']" in workflow
    assert "workflows.consumer-sync-plan/v1" in workflow
    assert "find templates/consumer-repo -type f" not in workflow
    assert ".github/templates" in workflow
    assert ".github/PULL_REQUEST_TEMPLATE.md" in workflow
    assert ".github/path-classification.yml" in workflow
