from __future__ import annotations

import os
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from tools.integration_repo import WORKFLOW_PLACEHOLDER, render_integration_repo


def test_integration_template_installs_and_tests(tmp_path: Path) -> None:
    destination = tmp_path / "consumer"
    workflow_ref = "owner/repo/.github/workflows/reusable-10-ci-python.yml@ref"

    render_integration_repo(destination, workflow_ref=workflow_ref)

    workflow_file = destination / ".github" / "workflows" / "ci.yml"
    workflow_contents = workflow_file.read_text(encoding="utf-8")

    assert WORKFLOW_PLACEHOLDER not in workflow_contents
    assert workflow_ref in workflow_contents

    with (destination / "pyproject.toml").open("rb") as project:
        requires_python = tomllib.load(project)["project"]["requires-python"]
    if ".".join(map(str, sys.version_info[:3])) not in SpecifierSet(requires_python):
        pytest.skip(f"Rendered scaffold requires Python {requires_python}")

    # Exercise an actual install independently of the test runner's build dependencies.
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True, symlinks=os.name != "nt")
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([python, "-m", "pip", "install", "-e", ".[test]"], cwd=destination, check=True)
    subprocess.run([python, "-m", "pytest"], cwd=destination, check=True)


def _write_template_tree(root: Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        f"uses: {WORKFLOW_PLACEHOLDER}\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("Welcome\n", encoding="utf-8")
    (root / "bin.dat").write_bytes(b"\xff\xfe\x00\x01")


def test_render_integration_repo_rewrites_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_template_tree(template_root)
    monkeypatch.setattr("tools.integration_repo.TEMPLATE_ROOT", template_root, raising=False)

    destination = tmp_path / "consumer"
    workflow_ref = "octo/ci/.github/workflows/ci.yml@v1"

    render_integration_repo(destination, workflow_ref=workflow_ref)

    rendered = (destination / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert WORKFLOW_PLACEHOLDER not in rendered
    assert workflow_ref in rendered
    assert (destination / "README.md").read_text(encoding="utf-8") == "Welcome\n"
    assert (destination / "bin.dat").read_bytes() == b"\xff\xfe\x00\x01"


def test_render_integration_repo_uses_default_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import integration_repo

    template_root = tmp_path / "template"
    _write_template_tree(template_root)
    monkeypatch.setattr("tools.integration_repo.TEMPLATE_ROOT", template_root, raising=False)

    destination = tmp_path / "consumer"

    render_integration_repo(destination)

    rendered = (destination / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert integration_repo.DEFAULT_WORKFLOW_REF in rendered


def test_render_integration_repo_refuses_non_empty_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_template_tree(template_root)
    monkeypatch.setattr("tools.integration_repo.TEMPLATE_ROOT", template_root, raising=False)

    destination = tmp_path / "consumer"
    destination.mkdir()
    (destination / "existing.txt").write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError):
        render_integration_repo(destination)


def test_render_integration_repo_requires_template_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_root = tmp_path / "missing"
    monkeypatch.setattr("tools.integration_repo.TEMPLATE_ROOT", missing_root, raising=False)

    destination = tmp_path / "consumer"

    with pytest.raises(FileNotFoundError):
        render_integration_repo(destination)
