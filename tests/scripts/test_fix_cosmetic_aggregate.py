from pathlib import Path

from scripts import fix_cosmetic_aggregate


def test_main_returns_when_target_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fix_cosmetic_aggregate, "ROOT", Path(tmp_path))
    monkeypatch.setattr(fix_cosmetic_aggregate, "TARGET", Path("missing.py"))

    assert fix_cosmetic_aggregate.main() == 0
