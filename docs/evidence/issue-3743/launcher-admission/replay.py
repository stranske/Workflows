"""Replay four launcher-admission production mutations in private copies.

Run with the intended Python interpreter and a new --output directory. The
checkout's production and historical evidence files are never modified.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from defusedxml import ElementTree

ROOT = Path(__file__).resolve().parents[4]
SOURCE = "scripts/check_deliberate_break.py"
TEST = "tests/scripts/test_check_deliberate_break_launcher_admission.py"
NAME = "test_unavailable_or_non_python_pytest_does_not_admit_active_runtime"
MUTATIONS = {
    "missing": (
        "if not pytest_path:\n            return False",
        "if not pytest_path:\n            return True",
    ),
    "opaque": (
        "if launcher is None:\n            return False",
        "if launcher is None:\n            return True",
    ),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipts = []
    for variant, prefix in (("root", ""), ("template", "templates/consumer-repo/")):
        for launcher, (old, new) in MUTATIONS.items():
            label = f"{variant}-{launcher}"
            with tempfile.TemporaryDirectory(prefix="launcher-admission-") as private:
                work = Path(private)
                for relative in (SOURCE, "templates/consumer-repo/" + SOURCE, TEST):
                    target = work / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / relative, target)
                target = work / prefix / SOURCE
                original = target.read_bytes()
                text = original.decode()
                require(text.count(old) == 1, "mutation anchor must be unique")
                target.write_text(text.replace(old, new), encoding="utf-8")
                mutant_hash = digest(target.read_bytes())
                phases = {}
                try:
                    for phase in ("red", "green"):
                        if phase == "green":
                            target.write_bytes(original)
                        report = output / f"{label}-{phase}.xml"
                        command = [
                            sys.executable,
                            "-m",
                            "pytest",
                            f"{TEST}::{NAME}[{label}]",
                            "-q",
                            "-o",
                            "addopts=",
                            f"--junitxml={report}",
                        ]
                        run = subprocess.run(
                            command, cwd=work, capture_output=True, text=True, timeout=120
                        )
                        (output / f"{label}-{phase}.log").write_text(run.stdout + run.stderr)
                        tree = ElementTree.parse(report)
                        cases = list(tree.iter("testcase"))
                        require(len(cases) == 1, "expected exactly one selected case")
                        case = cases[0]
                        require(
                            case.find("error") is None and case.find("skipped") is None,
                            "errors and skips do not prove detection",
                        )
                        failure = case.find("failure")
                        require(
                            run.returncode == (1 if phase == "red" else 0), "unexpected pytest exit"
                        )
                        require(
                            (failure is not None) == (phase == "red"), "wrong assertion outcome"
                        )
                        if failure is not None:
                            require(
                                "assert True is False" in (failure.text or ""),
                                "mutation must fail the intended admission assertion",
                            )
                        phases[phase] = {
                            "argv": command,
                            "cwd": str(work),
                            "exit": run.returncode,
                            "node": case.attrib,
                            "source_sha256": digest(target.read_bytes()),
                        }
                finally:
                    target.write_bytes(original)
                require(digest(target.read_bytes()) == digest(original), "restoration differs")
                receipts.append(
                    {
                        "case": label,
                        "original_sha256": digest(original),
                        "mutant_sha256": mutant_hash,
                        "phases": phases,
                    }
                )
    (output / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print("4 assertion RED / byte-identical restoration GREEN pairs")


if __name__ == "__main__":
    main()
