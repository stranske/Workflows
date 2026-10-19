#!/usr/bin/env python3
"""Reproducible deliberate-break gate for verification-binding audit (#3968).

Applies a temporary Scope change to scripts/langchain/verifier_config.py and a
temporary regression in tests/scripts/test_verifier_config.py, records pass with
the fix, fail when the fix is disconnected, then restores both files
byte-for-byte. Permanent audit PR content stays under docs/reports/ only.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = REPO_ROOT / "scripts" / "langchain" / "verifier_config.py"
TEST_PATH = REPO_ROOT / "tests" / "scripts" / "test_verifier_config.py"
OUT_DIR = Path(__file__).resolve().parent / "deliberate-break"
REGRESSION_NODE = (
    "tests/scripts/test_verifier_config.py::"
    "test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete"
)
POSITIVE_NODE = (
    "tests/scripts/test_verifier_config.py::"
    "test_artifact_from_verification_text_accepts_terminal_verdict_on_latest_report"
)

REGRESSION_BLOCK = '''

def test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete() -> None:
    """Latest incomplete report must not inherit a historical PASS verdict."""

    text = (
        "## PR Verification Report\\nVerdict: PASS\\n\\n"
        "## PR Verification Report\\n"
        "Context extraction failed before any provider returned."
    )
    artifact = artifact_from_verification_text(text)
    assert "verdict" not in artifact
    assert is_terminal_artifact(artifact) is False


def test_artifact_from_verification_text_accepts_terminal_verdict_on_latest_report() -> None:
    """A complete latest report still supplies its own terminal verdict."""

    text = (
        "## PR Verification Report\\nVerdict: FAIL\\n\\n"
        "## PR Verification Report\\nVerdict: PASS\\n"
    )
    artifact = artifact_from_verification_text(text)
    assert artifact.get("verdict") == "PASS"
    assert is_terminal_artifact(artifact) is True
'''


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize_transcript(blob: bytes) -> bytes:
    """Drop pytest wall-clock noise so deliberate-break receipts stay reproducible."""

    text = blob.decode("utf-8", errors="replace")
    # "2 passed in 0.94s" / "1 failed in 0.23s" — duration is not evidence.
    text = re.sub(
        r"\b(\d+ (?:passed|failed|skipped|xfailed|xpassed|error|errors)) in [0-9.]+s\b",
        r"\1 in <time>",
        text,
    )
    # Rare pytest variants: "in 1.23s =" suffixes on progress lines.
    text = re.sub(r"\bin [0-9.]+s\b", "in <time>", text)
    return text.encode("utf-8")


def _write_transcript(name: str, payload: bytes) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_transcript(payload)
    path = OUT_DIR / name
    path.write_bytes(normalized)
    digest = _sha256_bytes(normalized)
    (OUT_DIR / f"{name}.sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def _run_pytest(nodes: list[str]) -> subprocess.CompletedProcess[bytes]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *nodes,
        "-o",
        "addopts=",
        "-m",
        "not slow",
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True)


def _summarize_pytest(blob: bytes) -> str:
    text = _normalize_transcript(blob).decode("utf-8", errors="replace")
    for pattern, label in (
        (r"(\d+) failed", "failed"),
        (r"(\d+) passed", "passed"),
    ):
        match = re.search(pattern, text)
        if match:
            return f"{match.group(1)} {label}"
    raise RuntimeError("could not summarize pytest transcript:\n" + text)


def _apply_scope_fix(source: str) -> str:
    """Extract verdicts from the latest report only (Scope change for #3966)."""

    pattern = (
        r"    verdicts = _extract_verdicts\(raw\)\n"
        r"    if verdicts:\n"
        r"        severity = \{[^}]+\}\n"
        r"        artifact\[\"verdict\"\] = max\(verdicts, key=lambda verdict: severity\.get\(verdict, -1\)\)\n"
        r"\n"
        r"    latest_raw = _latest_verifier_report\(raw\)\n"
    )
    replacement = (
        "    latest_raw = _latest_verifier_report(raw)\n"
        "    verdicts = _extract_verdicts(latest_raw)\n"
        "    if verdicts:\n"
        '        severity = {"PASS": 0, "CONCERNS": 1, "FAIL": 2, "ERROR": 3, "UNVERIFIABLE_INPUT": 0.5}\n'
        '        artifact["verdict"] = max(verdicts, key=lambda verdict: severity.get(verdict, -1))\n'
        "\n"
    )
    updated, count = re.subn(pattern, replacement, source, count=1)
    if count != 1:
        raise RuntimeError(
            "failed to locate artifact_from_verification_text verdict extraction block"
        )
    return updated


def _disconnect_scope_fix(fixed: str) -> str:
    """Restore full-history verdict scanning while keeping the temporary tests."""

    pattern = (
        r"    latest_raw = _latest_verifier_report\(raw\)\n"
        r"    verdicts = _extract_verdicts\(latest_raw\)\n"
        r"    if verdicts:\n"
        r"        severity = \{[^}]+\}\n"
        r"        artifact\[\"verdict\"\] = max\(verdicts, key=lambda verdict: severity\.get\(verdict, -1\)\)\n"
        r"\n"
    )
    replacement = (
        "    verdicts = _extract_verdicts(raw)\n"
        "    if verdicts:\n"
        '        severity = {"PASS": 0, "CONCERNS": 1, "FAIL": 2, "ERROR": 3, "UNVERIFIABLE_INPUT": 0.5}\n'
        '        artifact["verdict"] = max(verdicts, key=lambda verdict: severity.get(verdict, -1))\n'
        "\n"
        "    latest_raw = _latest_verifier_report(raw)\n"
    )
    updated, count = re.subn(pattern, replacement, fixed, count=1)
    if count != 1:
        raise RuntimeError("failed to disconnect Scope change for deliberate-break")
    return updated


def main() -> int:
    original_config = CONFIG_PATH.read_bytes()
    original_test = TEST_PATH.read_bytes()
    original_config_text = original_config.decode("utf-8")
    original_test_text = original_test.decode("utf-8")

    marker = "test_artifact_from_verification_text_ignores_historical_pass_when_latest_incomplete"
    if marker in original_test_text:
        raise RuntimeError(
            "regression already present in working tree; aborting to avoid double-append"
        )

    try:
        fixed_config = _apply_scope_fix(original_config_text)
        CONFIG_PATH.write_text(fixed_config, encoding="utf-8")
        TEST_PATH.write_text(original_test_text + REGRESSION_BLOCK, encoding="utf-8")

        with_fix = _run_pytest([REGRESSION_NODE, POSITIVE_NODE])
        with_fix_blob = with_fix.stdout + b"\n--- stderr ---\n" + with_fix.stderr
        with_fix_sha = _write_transcript("with_fix.pytest.txt", with_fix_blob)
        if with_fix.returncode != 0:
            raise RuntimeError(
                f"expected with-fix run to pass, got {with_fix.returncode}:\n"
                + with_fix_blob.decode("utf-8", errors="replace")
            )

        CONFIG_PATH.write_text(_disconnect_scope_fix(fixed_config), encoding="utf-8")
        # Scope AC targets the historical-PASS regression only when disconnected.
        disconnected = _run_pytest([REGRESSION_NODE])
        disconnected_blob = disconnected.stdout + b"\n--- stderr ---\n" + disconnected.stderr
        disconnected_sha = _write_transcript("fix_disconnected.pytest.txt", disconnected_blob)
        if disconnected.returncode == 0:
            raise RuntimeError(
                "expected disconnected Scope change to fail the historical-PASS regression"
            )
        disconnected_text = disconnected_blob.decode("utf-8", errors="replace")
        if "verdict" not in disconnected_text or "PASS" not in disconnected_text:
            raise RuntimeError(
                "disconnected failure did not show inherited PASS/verdict assertion:\n"
                + disconnected_text
            )
        if "AssertionError" not in disconnected_text:
            raise RuntimeError(
                "disconnected run did not fail with AssertionError:\n" + disconnected_text
            )

        CONFIG_PATH.write_text(fixed_config, encoding="utf-8")
        restored = _run_pytest([REGRESSION_NODE, POSITIVE_NODE])
        restored_blob = restored.stdout + b"\n--- stderr ---\n" + restored.stderr
        restored_sha = _write_transcript("fix_restored.pytest.txt", restored_blob)
        if restored.returncode != 0:
            raise RuntimeError(
                f"expected restored Scope change to pass, got {restored.returncode}:\n"
                + restored_blob.decode("utf-8", errors="replace")
            )
    finally:
        CONFIG_PATH.write_bytes(original_config)
        TEST_PATH.write_bytes(original_test)

    if CONFIG_PATH.read_bytes() != original_config or TEST_PATH.read_bytes() != original_test:
        raise RuntimeError("working tree not restored byte-for-byte")

    # Idempotence guard: normalized transcripts must hash stably across re-runs.
    for label, blob, digest in (
        ("with_fix", with_fix_blob, with_fix_sha),
        ("fix_disconnected", disconnected_blob, disconnected_sha),
        ("fix_restored", restored_blob, restored_sha),
    ):
        again = _sha256_bytes(_normalize_transcript(blob))
        if again != digest:
            raise RuntimeError(f"transcript normalization not idempotent for {label}")

    receipt = {
        "regression": REGRESSION_NODE,
        "positive_control": POSITIVE_NODE,
        "scope_change": (
            "scripts/langchain/verifier_config.py artifact_from_verification_text: "
            "extract verdicts from _latest_verifier_report(raw) only"
        ),
        "transcript_normalization": "pytest wall-clock durations replaced with <time>",
        "with_fix": {
            "result": _summarize_pytest(with_fix_blob),
            "sha256": with_fix_sha,
        },
        "fix_disconnected": {
            "result": _summarize_pytest(disconnected_blob),
            "assertion": (
                "assert 'verdict' not in artifact; observed verdict PASS from historical report"
            ),
            "sha256": disconnected_sha,
        },
        "fix_restored": {
            "result": _summarize_pytest(restored_blob),
            "sha256": restored_sha,
        },
        "working_tree_restored": True,
        "config_sha256_after": _sha256_bytes(CONFIG_PATH.read_bytes()),
        "test_sha256_after": _sha256_bytes(TEST_PATH.read_bytes()),
    }
    receipt_path = OUT_DIR / "receipt.json"
    receipt_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    receipt_path.write_bytes(receipt_bytes)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
