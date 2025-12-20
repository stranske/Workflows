from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import scripts.auto_type_hygiene as auto_type_hygiene
from scripts.auto_type_hygiene import process_file


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Command {' '.join(cmd)} failed with {result.returncode}:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


@pytest.mark.integration
def test_autofix_pipeline_fixes_trivial_ruff_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("ruff")
    pytest.importorskip("isort")
    pytest.importorskip("docformatter")
    pytest.importorskip("black")

    # Ensure the type-hygiene helper treats ``yaml`` as untyped even if local
    # test stubs exist elsewhere in the repository.
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [tmp_path], raising=False)

    sample = tmp_path / "bad_format.py"
    sample.write_text(
        'import os\nimport yaml\n\n\ndef add(a,b):\n    yaml.safe_load("[]")\n    return  a + b\n',
        encoding="utf-8",
    )

    fail = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        capture_output=True,
        text=True,
    )
    assert fail.returncode != 0, "Expected initial ruff check to fail"

    commands = [
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
        [sys.executable, "-m", "isort", str(sample)],
        [sys.executable, "-m", "docformatter", "-i", str(sample)],
        [sys.executable, "-m", "black", str(sample)],
        [sys.executable, "-m", "ruff", "check", "--fix", "--exit-zero", str(sample)],
    ]

    for cmd in commands:
        _run(cmd, cwd=tmp_path)

    changed, new_lines = process_file(sample)
    assert changed is False
    if changed:
        sample.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    final = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(sample)],
        capture_output=True,
        text=True,
    )
    assert final.returncode == 0, final.stderr

    content = sample.read_text(encoding="utf-8")
    assert "type: ignore" not in content
    assert "return a + b" in content


def test_auto_type_hygiene_adds_ignore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample = tmp_path / "module.py"
    sample.write_text("import untyped_mod\n", encoding="utf-8")

    module_name = "untyped_mod"
    monkeypatch.setattr(auto_type_hygiene, "ALLOWLIST", [module_name])
    monkeypatch.setattr(auto_type_hygiene, "SRC_DIRS", [], raising=False)

    changed, new_lines = process_file(sample)
    assert changed
    assert new_lines[0].endswith("# type: ignore[import-untyped, unused-ignore]")
