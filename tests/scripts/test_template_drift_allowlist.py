from __future__ import annotations

import configparser
from pathlib import Path

from scripts.check_template_drift import read_allowlist

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "config/template-drift-allowlist.txt"


def test_every_pair_states_its_divergence() -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ALLOWLIST, encoding="utf-8")

    assert ALLOWLIST.name == "template-drift-allowlist.txt"
    assert len(parser.sections()) >= 1

    for section in parser.sections():
        divergence = parser.get(section, "divergence", fallback="").strip()
        reviewed = parser.get(section, "divergence_reviewed", fallback="").strip()
        refreshed = parser.get(section, "fingerprint_refreshed", fallback="").strip()
        assert divergence and "Existing reviewed baseline drift" not in divergence
        assert reviewed
        assert refreshed


def test_read_allowlist_prefers_divergence_and_supports_legacy_reason(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.txt"
    allowlist_path.write_text(
        """
[pair.current]
main = root.yml
template = template.yml
main_sha256 = main-current
template_sha256 = template-current
divergence = current rationale
reason = superseded legacy rationale

[pair.legacy]
main = legacy-root.yml
template = legacy-template.yml
main_sha256 = main-legacy
template_sha256 = template-legacy
reason = legacy rationale
""".strip()
        + "\n",
        encoding="utf-8",
    )

    entries = read_allowlist(allowlist_path).entries

    assert [entry.reason for entry in entries] == ["current rationale", "legacy rationale"]
