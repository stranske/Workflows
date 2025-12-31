from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.integration_repo import WORKFLOW_PLACEHOLDER, render_integration_repo


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def test_integration_template_installs_and_tests(tmp_path: Path) -> None:
    destination = tmp_path / "consumer"
    workflow_ref = "owner/repo/.github/workflows/reusable-10-ci-python.yml@ref"

    render_integration_repo(destination, workflow_ref=workflow_ref)

    workflow_file = destination / ".github" / "workflows" / "ci.yml"
    workflow_contents = workflow_file.read_text(encoding="utf-8")

    assert WORKFLOW_PLACEHOLDER not in workflow_contents
    assert workflow_ref in workflow_contents

    user_base = tmp_path / "userbase"
    env = os.environ.copy()
    env["PYTHONUSERBASE"] = str(user_base)

    if importlib.util.find_spec("wheel") is None:
        pytest.skip("wheel is unavailable in the test environment")
    try:
        metadata.version("setuptools")
    except metadata.PackageNotFoundError:
        pytest.skip("setuptools is unavailable in the test environment")

    # Install setuptools first (required for --no-build-isolation with pyproject.toml builds)
    _run(
        [sys.executable, "-m", "pip", "install", "setuptools>=64", "wheel", "--user"],
        cwd=destination,
        env=env,
    )

    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-e",
            ".[test]",
            "--no-build-isolation",
            "--user",
        ],
        cwd=destination,
        env=env,
    )
    _run([sys.executable, "-m", "pytest"], cwd=destination, env=env)


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
