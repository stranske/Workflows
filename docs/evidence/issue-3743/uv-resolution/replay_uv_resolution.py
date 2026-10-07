"""Replay eight production mutations in a private tree; never mutate caller files."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from defusedxml import ElementTree as ET

TEST = "tests/scripts/test_check_deliberate_break_uv_resolution.py"
HELPER = "scripts/check_deliberate_break.py"
MUTATIONS = {
    "pytest-nonzero": (
        "if located.returncode != 0 or not located.stdout.strip():",
        "if not located.stdout.strip():",
    ),
    "pytest-empty": (
        "if located.returncode != 0 or not located.stdout.strip():",
        "if located.returncode != 0:",
    ),
    "python-nonzero": (
        "if resolved.returncode != 0 or not resolved.stdout.strip():",
        "if not resolved.stdout.strip():",
    ),
    "python-empty": (
        "if resolved.returncode != 0 or not resolved.stdout.strip():",
        "if resolved.returncode != 0:",
    ),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run_case(tree, output, node, phase):
    xml = output / f"{phase}.xml"
    argv = [sys.executable, "-m", "pytest", node, "-q", "-o", "addopts=", f"--junitxml={xml}"]
    with (output / f"{phase}.log").open("w", encoding="utf-8") as log:
        process = subprocess.run(argv, cwd=tree, stdout=log, stderr=subprocess.STDOUT, timeout=120)
    cases = list(ET.parse(xml).getroot().iter("testcase"))
    expected = 1 if phase == "red" else 0
    assert process.returncode == expected, (node, phase, process.returncode)
    assert len(cases) == 1 and not list(cases[0].iter("error")), (node, phase)
    assert bool(list(cases[0].iter("failure"))) is (phase == "red"), (node, phase)
    assert not list(cases[0].iter("skipped")), (node, phase)
    receipt = {"argv": argv, "cwd": str(tree), "exit": process.returncode, "node": node}
    (output / f"{phase}.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[4]
    identities = {
        path: digest((root / path).read_bytes())
        for path in [
            TEST,
            HELPER,
            "templates/consumer-repo/" + HELPER,
            str(Path(__file__).resolve().relative_to(root)),
        ]
    }
    controls = []
    with tempfile.TemporaryDirectory(prefix="uv-resolution-proof-") as temporary:
        tree = Path(temporary)
        for relative in [TEST, HELPER, "templates/consumer-repo/" + HELPER]:
            destination = tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        for copy, prefix in [("root", ""), ("template", "templates/consumer-repo/")]:
            source = tree / prefix / HELPER
            original = source.read_bytes()
            for kind, (before, after) in MUTATIONS.items():
                case = output / f"{copy}-{kind}"
                case.mkdir()
                node = f"{TEST}::test_uv_resolution_refuses_failed_or_empty_lookup[{copy}-{kind}]"
                text = original.decode("utf-8")
                assert text.count(before) == 1, (copy, kind, "mutation anchor drift")
                mutated = text.replace(before, after).encode("utf-8")
                try:
                    source.write_bytes(mutated)
                    red = run_case(tree, case, node, "red")
                finally:
                    source.write_bytes(original)
                assert source.read_bytes() == original
                green = run_case(tree, case, node, "green")
                controls.append(
                    {
                        "copy": copy,
                        "kind": kind,
                        "original_sha256": digest(original),
                        "mutated_sha256": digest(mutated),
                        "restored_sha256": digest(source.read_bytes()),
                        "red": red,
                        "green": green,
                    }
                )
    assert len(controls) == 8
    assert identities == {path: digest((root / path).read_bytes()) for path in identities}
    (output / "controls.json").write_text(
        json.dumps({"caller_identity": identities, "controls": controls}, indent=2),
        encoding="utf-8",
    )
    print("8 named production mutations RED; 8 exact restorations GREEN; caller bytes unchanged")


if __name__ == "__main__":
    main()
