from pathlib import Path

from scripts import fix_cosmetic_aggregate


def test_main_returns_when_target_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", Path(tmp_path))
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", Path("missing.py"))

    assert fix_cosmetic_aggregate.main() == 0


def test_fix_cosmetic_aggregate_rewrites_supported_join_variants() -> None:
    rewritten, changed = fix_cosmetic_aggregate._rewrite('return ",".join(items)')
    assert changed is True
    assert '" | ".join(items)' in rewritten

    rewritten_single, changed_single = fix_cosmetic_aggregate._rewrite("return ','.join(items)")
    assert changed_single is True
    assert '" | ".join(items)' in rewritten_single


def test_fix_cosmetic_aggregate_main_noops_when_target_missing(tmp_path: Path, monkeypatch) -> None:
    missing_target = tmp_path / "automation_multifailure.py"
    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", tmp_path, raising=False)
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", missing_target, raising=False)

    assert fix_cosmetic_aggregate.main() == 0
