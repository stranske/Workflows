from __future__ import annotations

from pathlib import Path

import pytest

from scripts import fix_numpy_asserts


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_tracked_arrays_collects_names() -> None:
    lines = [
        "data = np.array([1, 2])",
        "skip = other.array([3])",
        "  sample=np.array([4])",
    ]

    names = fix_numpy_asserts._tracked_arrays(lines)

    assert names == {"data", "sample"}


def test_process_file_ignores_untracked_assert(tmp_path: Path) -> None:
    target = tmp_path / "test_case.py"
    _write_lines(
        target,
        [
            "import numpy as np",
            "values = [1, 2, 3]",
            "assert values == [1, 2, 3]",
        ],
    )

    changed = fix_numpy_asserts.process_file(target)

    assert changed is False
    assert target.read_text(encoding="utf-8") == (
        "import numpy as np\nvalues = [1, 2, 3]\nassert values == [1, 2, 3]\n"
    )


def test_main_scans_tests_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = tmp_path / "repo"
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True)
    target = tests_dir / "test_numpy.py"
    _write_lines(
        target,
        [
            "import numpy as np",
            "",
            "def test_case():",
            "    values = np.array([1, 2])",
            "    assert values == [1, 2]",
        ],
    )

    monkeypatch.setattr(fix_numpy_asserts, "ROOT", repo_root)
    monkeypatch.setattr(fix_numpy_asserts, "TEST_ROOT", Path("tests"))
    monkeypatch.setattr(fix_numpy_asserts, "TARGET_FILES", set())

    exit_code = fix_numpy_asserts.main()

    assert exit_code == 0
    assert "values.tolist()" in target.read_text(encoding="utf-8")
