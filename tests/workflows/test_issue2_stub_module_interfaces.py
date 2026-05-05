from __future__ import annotations

from pathlib import Path

import scripts.fix_cosmetic_aggregate as fix_cosmetic_aggregate
import scripts.mypy_return_autofix as mypy_return_autofix
import scripts.update_autofix_expectations as update_autofix_expectations


def test_fix_cosmetic_aggregate_rewrites_supported_join_variants() -> None:
    rewritten, changed = fix_cosmetic_aggregate._rewrite('return ",".join(items)')
    assert changed is True
    assert '" | ".join(items)' in rewritten

    rewritten_single, changed_single = fix_cosmetic_aggregate._rewrite("return ','.join(items)")
    assert changed_single is True
    assert '" | ".join(items)' in rewritten_single


def test_mypy_return_autofix_main_noops_when_targets_missing(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing-src"
    monkeypatch.setattr(mypy_return_autofix, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(mypy_return_autofix, "PROJECT_DIRS", [missing], raising=False)
    assert mypy_return_autofix.main() == 0


def test_update_autofix_expectations_main_noops_with_empty_targets() -> None:
    assert update_autofix_expectations.main([]) == 0


def test_fix_cosmetic_aggregate_main_noops_when_target_missing(tmp_path: Path, monkeypatch) -> None:
    missing_target = tmp_path / "automation_multifailure.py"
    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", missing_target, raising=False)

    assert fix_cosmetic_aggregate.main() == 0


def test_update_autofix_expectations_update_constant_handles_missing_callable() -> None:
    class DummyModule:
        __file__ = None

    target = update_autofix_expectations.AutofixTarget(
        module="dummy.module",
        callable_name="missing_callable",
        constant_name="EXPECTED_VALUE",
    )

    assert update_autofix_expectations._update_constant(DummyModule, target) is False
