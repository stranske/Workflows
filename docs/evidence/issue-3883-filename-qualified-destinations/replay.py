"""Reverse the filename-qualifier retention rule, then restore exact bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
    ROOT / "scripts/langchain/pr_verifier.py",
    ROOT / "templates/consumer-repo/scripts/langchain/pr_verifier.py",
)
DELIVERY = "tests/scripts/test_pr_verifier_delivery_destinations.py"
CALL = "    acceptance = _normalize_evidence_source_filename_qualifiers(acceptance)\n"
NODE_PREFIX = f"{DELIVERY}::"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mutant_bytes(fixed: bytes) -> bytes:
    text = fixed.decode()
    assert text.count(CALL) == 2, "expected dual channel/options normalizer calls"
    mutant = text.replace(CALL, "")
    assert mutant != text
    assert CALL not in mutant
    return mutant.encode()


def run(output: Path) -> dict:
    fixed = SOURCES[0].read_bytes()
    assert SOURCES[1].read_bytes() == fixed, "source/template mismatch before mutation"
    mutant = mutant_bytes(fixed)
    output.mkdir(parents=True, exist_ok=False)
    nodes = [
        f"{NODE_PREFIX}test_issue3883_filename_qualified_quantified_destinations",
        f"{NODE_PREFIX}test_issue3883_filename_qualified_both_requires_every_destination",
        f"{NODE_PREFIX}test_issue3883_filename_qualified_either_accepts_one_destination",
    ]
    receipt = {
        "fixed_sha256": digest(fixed),
        "mutant_sha256": digest(mutant),
        "nodes": nodes,
    }
    try:
        for source in SOURCES:
            assert source.read_bytes() == fixed, "unexpected source change before mutation"
            source.write_bytes(mutant)
        for phase, expected_exit in (("red", 1), ("green", 0)):
            if phase == "green":
                for source in SOURCES:
                    assert source.read_bytes() == mutant, "concurrent source edit"
                    source.write_bytes(fixed)
            argv = [
                sys.executable,
                "-m",
                "pytest",
                *nodes,
                "-q",
                "-o",
                "addopts=",
            ]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=180, check=False)
            (output / f"{phase}.stdout").write_bytes(result.stdout)
            (output / f"{phase}.stderr").write_bytes(result.stderr)
            receipt[phase] = {
                "argv": argv,
                "cwd": str(ROOT),
                "exit": result.returncode,
                "stdout_sha256": digest(result.stdout),
                "stderr_sha256": digest(result.stderr),
            }
            assert result.returncode == expected_exit, receipt
            if phase == "red":
                assert b"FAILED" in result.stdout or b"failed" in result.stdout
            else:
                assert b"failed" not in result.stdout.lower() or b"0 failed" in result.stdout
    finally:
        for source in SOURCES:
            current = source.read_bytes()
            if current == mutant:
                source.write_bytes(fixed)
            elif current != fixed:
                raise RuntimeError(f"Concurrent edit retained: {source}")
        receipt["restored_sha256"] = [digest(source.read_bytes()) for source in SOURCES]
    assert receipt["restored_sha256"] == [digest(fixed)] * 2
    (output / "receipts.json").write_text(json.dumps(receipt, indent=2) + "\n")
    hashes = {path.name: digest(path.read_bytes()) for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output.resolve()), indent=2))
