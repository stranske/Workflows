from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scripts import sync_integration_coverage_omit as sync_omit

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PYPROJECT = REPO_ROOT / "templates" / "integration-repo" / "pyproject.toml"


def test_template_declares_synced_tooling_omits() -> None:
    patterns = sync_omit.required_omit_patterns(TEMPLATE_PYPROJECT)
    for required in ("tests/*", "tools/*", "scripts/*", ".github/scripts/*"):
        assert required in patterns


def test_merge_omit_patterns_preserves_order_and_uniqueness() -> None:
    assert sync_omit.merge_omit_patterns(["tests/*", "tools/*"], ["tools/*", "scripts/*"]) == [
        "tests/*",
        "tools/*",
        "scripts/*",
    ]


def test_apply_coverage_omit_merges_into_existing_run_table(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text(
        "[tool.coverage.run]\n"
        'omit = ["tests/*"]\n'
        "branch = true\n"
        "[tool.coverage.report]\n"
        "precision = 2\n",
        encoding="utf-8",
    )
    required = ["tests/*", "tools/*", "scripts/*", ".github/scripts/*"]

    missing = sync_omit.apply_coverage_omit(target, required, apply=True)

    assert missing == ["tools/*", "scripts/*", ".github/scripts/*"]
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    assert data["tool"]["coverage"]["run"]["omit"] == required
    assert data["tool"]["coverage"]["run"]["branch"] is True
    assert data["tool"]["coverage"]["report"]["precision"] == 2


def test_apply_coverage_omit_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text(
        "[tool.coverage.run]\n"
        'omit = ["tests/*", "tools/*", "scripts/*", ".github/scripts/*"]\n'
        "branch = true\n",
        encoding="utf-8",
    )
    required = ["tests/*", "tools/*", "scripts/*", ".github/scripts/*"]

    assert sync_omit.apply_coverage_omit(target, required, apply=True) == []
    assert sync_omit.apply_coverage_omit(target, required, apply=True) == []


def test_apply_coverage_omit_creates_run_table_when_absent(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('[project]\nname = "example"\nversion = "0.1.0"\n', encoding="utf-8")
    required = ["tools/*", "scripts/*"]

    missing = sync_omit.apply_coverage_omit(target, required, apply=True)

    assert missing == required
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    assert data["tool"]["coverage"]["run"]["omit"] == required


def test_main_apply_updates_consumer_from_template(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('[tool.coverage.run]\nomit = ["tests/*"]\nbranch = true\n', encoding="utf-8")

    rc = sync_omit.main(
        ["--template", str(TEMPLATE_PYPROJECT), "--pyproject", str(target), "--apply"]
    )

    assert rc == 0
    data = tomllib.loads(target.read_text(encoding="utf-8"))
    for required in ("tests/*", "tools/*", "scripts/*", ".github/scripts/*"):
        assert required in data["tool"]["coverage"]["run"]["omit"]
    assert data["tool"]["coverage"]["run"]["branch"] is True


def test_main_check_mode_exits_nonzero_when_patterns_missing(tmp_path: Path) -> None:
    target = tmp_path / "pyproject.toml"
    target.write_text('[tool.coverage.run]\nomit = ["tests/*"]\n', encoding="utf-8")

    rc = sync_omit.main(["--template", str(TEMPLATE_PYPROJECT), "--pyproject", str(target)])

    assert rc == 1


def test_main_errors_when_paths_missing(tmp_path: Path) -> None:
    assert sync_omit.main(["--template", str(tmp_path / "missing.toml"), "--pyproject", "x"]) == 2
    assert (
        sync_omit.main(
            ["--template", str(TEMPLATE_PYPROJECT), "--pyproject", str(tmp_path / "missing.toml")]
        )
        == 2
    )


def test_required_omit_patterns_rejects_empty_template(tmp_path: Path) -> None:
    template = tmp_path / "pyproject.toml"
    template.write_text("[tool.coverage.run]\nbranch = true\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no \\[tool.coverage.run\\] omit"):
        sync_omit.required_omit_patterns(template)
