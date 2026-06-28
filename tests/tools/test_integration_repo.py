from __future__ import annotations

from pathlib import Path

import pytest
from tools import integration_repo
from tools.integration_repo import WORKFLOW_PLACEHOLDER, render_integration_repo


def _write_text_template(root: Path) -> None:
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(
        f"name: consumer\nuses: {WORKFLOW_PLACEHOLDER}\n",
        encoding="utf-8",
    )
    (root / "docs" / "nested").mkdir(parents=True)
    (root / "docs" / "nested" / "guide.md").write_text(
        f"Nested workflow ref: {WORKFLOW_PLACEHOLDER}\n",
        encoding="utf-8",
    )


def test_render_integration_repo_materializes_nested_files_with_explicit_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_text_template(template_root)
    monkeypatch.setattr(integration_repo, "TEMPLATE_ROOT", template_root)

    destination = tmp_path / "consumer"
    workflow_ref = "owner/repo/.github/workflows/reusable-10-ci-python.yml@feature"

    rendered_path = render_integration_repo(destination, workflow_ref=workflow_ref)

    assert rendered_path == destination
    workflow = (destination / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    guide = (destination / "docs" / "nested" / "guide.md").read_text(encoding="utf-8")
    assert WORKFLOW_PLACEHOLDER not in workflow
    assert WORKFLOW_PLACEHOLDER not in guide
    assert workflow_ref in workflow
    assert workflow_ref in guide


def test_render_integration_repo_uses_default_workflow_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_text_template(template_root)
    monkeypatch.setattr(integration_repo, "TEMPLATE_ROOT", template_root)

    destination = tmp_path / "consumer"

    render_integration_repo(destination)

    workflow = (destination / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert integration_repo.DEFAULT_WORKFLOW_REF in workflow


def test_render_integration_repo_copies_binary_files_when_text_decode_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_text_template(template_root)
    binary_payload = b"\xff\xfe\x00\x01"
    (template_root / "assets").mkdir()
    (template_root / "assets" / "logo.bin").write_bytes(binary_payload)
    monkeypatch.setattr(integration_repo, "TEMPLATE_ROOT", template_root)

    destination = tmp_path / "consumer"

    render_integration_repo(destination)

    assert (destination / "assets" / "logo.bin").read_bytes() == binary_payload


def test_render_integration_repo_refuses_non_empty_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template_root = tmp_path / "template"
    _write_text_template(template_root)
    monkeypatch.setattr(integration_repo, "TEMPLATE_ROOT", template_root)
    destination = tmp_path / "consumer"
    destination.mkdir()
    (destination / "existing.txt").write_text("occupied\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        render_integration_repo(destination)


def test_render_integration_repo_requires_existing_template_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(integration_repo, "TEMPLATE_ROOT", tmp_path / "missing-template")

    with pytest.raises(FileNotFoundError):
        render_integration_repo(tmp_path / "consumer")
