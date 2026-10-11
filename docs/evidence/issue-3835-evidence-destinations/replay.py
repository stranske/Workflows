"""Reverse each repaired grammar rule, then restore exact bytes and rerun its gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
    ROOT / "scripts/langchain/pr_verifier.py",
    ROOT / "templates/consumer-repo/scripts/langchain/pr_verifier.py",
)
DELIVERY = "tests/scripts/test_pr_verifier_delivery_destinations.py"
FLOOR = "tests/scripts/test_pr_verifier_prompt_coverage.py"
CASES = (
    ("artifact", "Attach evidence as an artifact", "artifacts"),
    ("review_comment", "Evidence must be posted in a PR review comment", "comments"),
    ("validation_output", "- [ ] Validation output in a PR comment", "comments"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mutations(fixed: bytes) -> dict[str, bytes]:
    text = fixed.decode()
    anchor = text.index("                explicit_artifact_delivery = bool(")
    start = text.index(
        '                    or re.search(\n                        r"\\b"\n'
        "                        + delivery_operation\n",
        anchor,
    )
    end = text.index(
        '                    or re.search(\n                        r"\\b"\n'
        "                        + mandatory_auxiliary\n",
        start,
    )
    comment = "    acceptance = _normalize_review_comment_destinations(acceptance)\n"
    assert text.count(comment) == 2
    checklist = (
        '        r"(?:evidence|command outputs?|transcripts?|" '
        '+ _EVIDENCE_PROOF_ALIAS_NOUN + r"))\\s+"\n'
    )
    assert text.count(checklist) == 1
    return {
        "artifact": (text[:start] + text[end:]).encode(),
        "review_comment": text.replace(comment, "").encode(),
        "validation_output": text.replace(
            checklist, '        r"(?:evidence|command outputs?|transcripts?))\\s+"\n'
        ).encode(),
    }


def run(output: Path) -> list[dict]:
    fixed = SOURCES[0].read_bytes()
    assert SOURCES[1].read_bytes() == fixed, "source/template mismatch before mutation"
    variants = mutations(fixed)  # Validate every anchor before any write.
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for name, criterion, channel in CASES:
        nodes = [f"{DELIVERY}::test_issue3835_delivery_destinations[{criterion}-{channel}]"]
        nodes += [
            f"{FLOOR}::test_issue3835_named_destination_cannot_borrow_present_body"
            f"[{missing}-{criterion}-{channel}]"
            for missing in ("absent", "unavailable")
        ]
        mutant = variants[name]
        receipt = {"case": name, "fixed_sha256": digest(fixed), "mutant_sha256": digest(mutant)}
        assert mutant != fixed
        for source in SOURCES:
            assert source.read_bytes() == fixed, "unexpected source change before mutation"
        try:
            for source in SOURCES:
                source.write_bytes(mutant)
            phases = [("red", 1), ("green", 0)]
            for phase, expected in phases:
                if phase == "green":
                    for source in SOURCES:
                        assert source.read_bytes() == mutant, "concurrent source edit"
                        source.write_bytes(fixed)
                junit = output / f"{name}-{phase}.xml"
                argv = [
                    sys.executable,
                    "-m",
                    "pytest",
                    *nodes,
                    "-q",
                    "-o",
                    "addopts=",
                    f"--junitxml={junit}",
                ]
                result = subprocess.run(
                    argv, cwd=ROOT, capture_output=True, timeout=120, check=False
                )
                (output / f"{name}-{phase}.stdout").write_bytes(result.stdout)
                (output / f"{name}-{phase}.stderr").write_bytes(result.stderr)
                tests = list(ET.parse(junit).iter("testcase"))
                failures = sum(test.find("failure") is not None for test in tests)
                errors = sum(test.find("error") is not None for test in tests)
                receipt[phase] = {
                    "argv": argv,
                    "cwd": str(ROOT),
                    "exit": result.returncode,
                    "tests": len(tests),
                    "failures": failures,
                    "errors": errors,
                }
                assert result.returncode == expected, receipt
                assert (
                    len(tests) == 3 and errors == 0 and failures == (3 if phase == "red" else 0)
                ), receipt
        finally:
            for source in SOURCES:
                current = source.read_bytes()
                if current == mutant:
                    source.write_bytes(fixed)
                elif current != fixed:
                    raise RuntimeError(f"Concurrent edit retained: {source}")
            receipt["restored_sha256"] = [digest(source.read_bytes()) for source in SOURCES]
            receipts.append(receipt)
            (output / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
        assert receipt["restored_sha256"] == [digest(fixed)] * 2
    hashes = {p.name: digest(p.read_bytes()) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps(hashes, indent=2) + "\n")
    return receipts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output.resolve()), indent=2))
