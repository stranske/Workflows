from __future__ import annotations

import configparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "config/template-drift-allowlist.txt"


def test_every_pair_states_its_divergence() -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ALLOWLIST, encoding="utf-8")

    for section in parser.sections():
        divergence = parser.get(section, "divergence", fallback="").strip()
        reviewed = parser.get(section, "divergence_reviewed", fallback="").strip()
        refreshed = parser.get(section, "fingerprint_refreshed", fallback="").strip()
        assert divergence and "Existing reviewed baseline drift" not in divergence
        assert reviewed
        assert refreshed
