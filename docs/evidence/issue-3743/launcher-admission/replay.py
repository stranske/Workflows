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
from xml.etree import ElementTree
from xml.parsers import expat

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


def validate_junit(report, label, phase):
    require(phase in {"red", "green"}, "unknown replay phase")
    text = report.read_text(encoding="utf-8")
    require(len(text.encode("utf-8")) <= 1024 * 1024, "oversized JUnit")
    parser = expat.ParserCreate()

    def reject(*args):
        raise ValueError("JUnit declarations and external entities are forbidden")

    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.Parse(text, True)
    tree = ElementTree.fromstring(text)
    cases = list(tree.iter("testcase"))
    require(len(cases) == 1, "expected exactly one selected case")
    case = cases[0]
    require(case.get("classname") == TEST[:-3].replace("/", "."), "wrong test module")
    require(case.get("name") == f"{NAME}[{label}]", "wrong selected case")
    require(
        case.find("error") is None and case.find("skipped") is None,
        "errors and skips do not prove detection",
    )
    failure = case.find("failure")
    require((failure is not None) == (phase == "red"), "wrong assertion outcome")
    if failure is not None:
        require(
            failure.get("type") in {None, "AssertionError"}
            and failure.get("message", "").startswith(
                ("AssertionError: assert True is False", "assert True is False")
            )
            and "assert True is False" in (failure.text or ""),
            "mutation must fail the intended admission assertion",
        )
    return case.attrib


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
                input_hashes = {
                    relative: digest((work / relative).read_bytes())
                    for relative in (SOURCE, "templates/consumer-repo/" + SOURCE, TEST)
                }
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
                            "-m",
                            "not slow",
                            f"--junitxml={report}",
                        ]
                        run = subprocess.run(
                            command, cwd=work, capture_output=True, text=True, timeout=120
                        )
                        (output / f"{label}-{phase}.log").write_text(run.stdout + run.stderr)
                        node = validate_junit(report, label, phase)
                        require(
                            run.returncode == (1 if phase == "red" else 0), "unexpected pytest exit"
                        )
                        phases[phase] = {
                            "argv": command,
                            "cwd": str(work),
                            "exit": run.returncode,
                            "node": node,
                            "source_sha256": digest(target.read_bytes()),
                            "test_sha256": digest((work / TEST).read_bytes()),
                        }
                finally:
                    target.write_bytes(original)
                require(digest(target.read_bytes()) == digest(original), "restoration differs")
                require(
                    all(
                        digest((work / relative).read_bytes()) == expected
                        for relative, expected in input_hashes.items()
                    ),
                    "private source or test input changed after restoration",
                )
                receipts.append(
                    {
                        "case": label,
                        "original_sha256": digest(original),
                        "restored_sha256": digest(target.read_bytes()),
                        "input_sha256": input_hashes,
                        "mutant_sha256": mutant_hash,
                        "phases": phases,
                    }
                )
    (output / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
    print("4 assertion RED / byte-identical restoration GREEN pairs")


if __name__ == "__main__":
    main()
