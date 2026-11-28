"""The verifier gzip limits are held in two languages; keep the two copies equal.

`.github/scripts/verifier_gzip_assets.js` (capture, delivered) and
`tools/verifier_gzip_assets.py` (decode, delivered) both enforce the per-file and cumulative
byte bounds. The JS side keeps the cumulative bounds as inline literals, so a change to one
copy would otherwise drift silently (cohesion review C2, 2026-11-28).
"""

from __future__ import annotations

import re
from pathlib import Path

from tools import verifier_gzip_assets

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / ".github" / "scripts" / "verifier_gzip_assets.js"


def _product(expression: str) -> int:
    value = 1
    for factor in expression.split("*"):
        value *= int(factor.strip())
    return value


def _js_limits(source: str) -> dict[str, int]:
    def one(pattern: str) -> int:
        matches = re.findall(pattern, source)
        assert len(matches) == 1, (pattern, matches)
        return _product(matches[0])

    return {
        "MAX_RAW": one(r"const MAX_RAW = ([0-9 *]+);"),
        "MAX_TEXT": one(r"const MAX_TEXT = ([0-9 *]+);"),
        "MAX_TOTAL_RAW": one(r"if \(rawTotal > ([0-9 *]+)\)"),
        "MAX_TOTAL_TEXT": one(r"if \(textTotal > ([0-9 *]+) \|\|"),
    }


def test_js_and_python_gzip_limits_match() -> None:
    js = _js_limits(JS.read_text(encoding="utf-8"))
    python = {name: getattr(verifier_gzip_assets, name) for name in js}
    assert js == python
    assert python == {
        "MAX_RAW": 4 * 1024 * 1024,
        "MAX_TEXT": 4 * 1024 * 1024,
        "MAX_TOTAL_RAW": 32 * 1024 * 1024,
        "MAX_TOTAL_TEXT": 64 * 1024 * 1024,
    }


def test_parity_check_detects_a_changed_js_bound() -> None:
    drifted = JS.read_text(encoding="utf-8").replace(
        "if (rawTotal > 32*1024*1024)", "if (rawTotal > 16*1024*1024)"
    )
    assert _js_limits(drifted)["MAX_TOTAL_RAW"] != verifier_gzip_assets.MAX_TOTAL_RAW
