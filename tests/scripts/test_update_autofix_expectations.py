from __future__ import annotations

import types
from pathlib import Path

from scripts import update_autofix_expectations


def test_update_constant_skips_missing_module_file(tmp_path: Path) -> None:
    module = types.ModuleType("sample")
    module.__file__ = str(tmp_path / "missing.py")

    def build() -> str:
        return "value"

    module.build = build
    target = update_autofix_expectations.AutofixTarget(
        module="sample",
        callable_name="build",
        constant_name="EXPECTED",
    )

    assert update_autofix_expectations._update_constant(module, target) is False


def test_update_constant_no_matching_constant(tmp_path: Path) -> None:
    module = types.ModuleType("sample")
    module_path = tmp_path / "sample.py"
    module_path.write_text("OTHER = 'value'\n", encoding="utf-8")
    module.__file__ = str(module_path)

    def build() -> str:
        return "new"

    module.build = build
    target = update_autofix_expectations.AutofixTarget(
        module="sample",
        callable_name="build",
        constant_name="EXPECTED",
    )

    assert update_autofix_expectations._update_constant(module, target) is False
    assert module_path.read_text(encoding="utf-8") == "OTHER = 'value'\n"


def test_update_constant_rewrites_matching_constant(tmp_path: Path) -> None:
    module = types.ModuleType("sample")
    module_path = tmp_path / "sample.py"
    module_path.write_text("EXPECTED = 'old'\nOTHER = 1\n", encoding="utf-8")
    module.__file__ = str(module_path)

    def build() -> str:
        return "new"

    module.build = build
    target = update_autofix_expectations.AutofixTarget(
        module="sample",
        callable_name="build",
        constant_name="EXPECTED",
    )

    assert update_autofix_expectations._update_constant(module, target) is True
    assert "EXPECTED = 'new'" in module_path.read_text(encoding="utf-8")
