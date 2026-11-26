"""Contract checks for the Health 70 managed-target exit validator."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.validate_sync_target_dispositions import main

TARGET = ".github/copilot-skills"
BASE = {
    "version": 1,
    "copilot_config": [
        {"source": f"{TARGET}/", "is_directory": True},
        {"source": "shared.md", "target": "docs/shared.md", "sync_mode": "create_only"},
    ],
}
RETAINED = {"source": "shared.md", "target": "docs/shared.md"}


def run_validator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], candidate: dict[str, Any]
) -> tuple[int, str]:
    base = tmp_path / "base.yml"
    manifest = tmp_path / "candidate.yml"
    base.write_text(yaml.safe_dump(BASE))
    manifest.write_text(yaml.safe_dump({"version": 1, **candidate}))
    result = main(["--base-manifest", str(base), "--manifest", str(manifest)])
    return result, capsys.readouterr().out


def test_unexplained_directory_exit_names_the_managed_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = run_validator(tmp_path, capsys, {"copilot_config": [RETAINED]})
    assert result == 1
    assert f"Managed sync target {TARGET!r} disappeared" in output
    assert "docs/shared.md" not in output


@pytest.mark.parametrize(
    "disposition",
    [
        {"removals": [{"target": TARGET, "description": "Retired reference files"}]},
        {"excluded": [{"path": f"{TARGET}/", "reason": "Receivers own their references"}]},
    ],
    ids=["remove", "keep-consumer-owned"],
)
def test_explicit_directory_dispositions_are_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], disposition: dict[str, Any]
) -> None:
    result, output = run_validator(tmp_path, capsys, {"copilot_config": [RETAINED], **disposition})
    assert result == 0
    assert "Validated dispositions for 1 departed" in output


def test_same_destination_survives_source_or_section_move(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = run_validator(
        tmp_path,
        capsys,
        {
            "docs": [{"source": "renamed.md", "target": "docs/shared.md"}],
            "copilot_config": [
                {"source": "new-skills-root", "target": TARGET, "is_directory": True}
            ],
        },
    )
    assert result == 0
    assert "Validated dispositions for 0 departed" in output


def test_target_rename_requires_a_disposition_for_the_old_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = run_validator(
        tmp_path,
        capsys,
        {
            "copilot_config": [
                {"source": TARGET, "is_directory": True},
                {"source": "shared.md", "target": "docs/moved.md"},
            ]
        },
    )
    assert result == 1
    assert "Managed sync target 'docs/shared.md' disappeared" in output


def test_broad_or_descendant_exclusion_cannot_cover_the_departed_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = run_validator(
        tmp_path,
        capsys,
        {
            "copilot_config": [RETAINED],
            "excluded": [
                {"path": ".github", "reason": "Parent directory"},
                {"path": f"{TARGET}/*", "reason": "Pattern"},
                {"path": f"{TARGET}/README.md", "reason": "Only one leaf"},
            ],
        },
    )
    assert result == 1
    assert f"Managed sync target {TARGET!r} disappeared" in output


def test_exclusion_without_a_reason_cannot_authorize_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result, output = run_validator(
        tmp_path,
        capsys,
        {"copilot_config": [RETAINED], "excluded": [{"path": TARGET, "reason": "  "}]},
    )
    assert result == 1
    assert f"exclusion for {TARGET!r} needs a reason" in output
