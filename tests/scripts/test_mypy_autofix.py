from __future__ import annotations

from pathlib import Path

import scripts.mypy_autofix as mypy_autofix


def test_ensure_typing_imports_no_needed(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("def foo(x: int) -> int:\n    return x\n", encoding="utf-8")

    assert not mypy_autofix._ensure_typing_imports(sample, {"Optional", "Iterable"})
    assert sample.read_text(encoding="utf-8") == "def foo(x: int) -> int:\n    return x\n"


def test_ensure_typing_imports_merges_existing_import(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from typing import Iterable\n\n"
        "def foo(x: Optional[int], y: Iterable[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    assert mypy_autofix._ensure_typing_imports(sample, {"Optional", "Iterable"})
    assert sample.read_text(encoding="utf-8").splitlines()[0] == "from typing import Iterable, Optional"


def test_ensure_typing_imports_no_missing_in_existing_import(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from typing import Iterable, Optional\n\n"
        "def foo(x: Optional[int], y: Iterable[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    assert not mypy_autofix._ensure_typing_imports(sample, {"Optional", "Iterable"})
    assert sample.read_text(encoding="utf-8").splitlines()[0] == "from typing import Iterable, Optional"


def test_ensure_typing_imports_inserts_after_future(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from __future__ import annotations\n\n"
        "def foo(x: Optional[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    assert mypy_autofix._ensure_typing_imports(sample, {"Optional", "Iterable"})
    lines = sample.read_text(encoding="utf-8").splitlines()
    assert lines[:3] == [
        "from __future__ import annotations",
        "",
        "from typing import Optional",
    ]


def test_main_processes_files_and_dirs(tmp_path: Path, monkeypatch) -> None:
    sample_file = tmp_path / "sample.py"
    sample_file.write_text(
        "def foo(x: Optional[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    sample_dir = tmp_path / "pkg"
    sample_dir.mkdir()
    module_file = sample_dir / "mod.py"
    module_file.write_text(
        "def bar(items: Iterable[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mypy_autofix, "ROOT", tmp_path)

    assert mypy_autofix.main(["--paths", "sample.py"]) == 0
    assert "from typing import Optional" in sample_file.read_text(encoding="utf-8")

    assert mypy_autofix.main(["--paths", "pkg"]) == 0
    assert "from typing import Iterable" in module_file.read_text(encoding="utf-8")
    assert mypy_autofix.main(["--paths", "missing.py"]) == 0


def test_main_uses_default_targets(tmp_path: Path, monkeypatch) -> None:
    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    default_file = defaults_dir / "default.py"
    default_file.write_text(
        "def baz(items: Iterable[int]) -> None:\n"
        "    pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mypy_autofix, "ROOT", tmp_path)
    monkeypatch.setattr(mypy_autofix, "DEFAULT_TARGETS", [defaults_dir])

    assert mypy_autofix.main([]) == 0
    assert "from typing import Iterable" in default_file.read_text(encoding="utf-8")
