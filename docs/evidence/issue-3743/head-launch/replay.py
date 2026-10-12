"""Replay four head-launch production verdict mutations in private copies.

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
TEST = "tests/scripts/test_check_deliberate_break_head_launch.py"
NAME = "test_unavailable_head_command_is_reported_without_base_or_repair"
MUTATIONS = dict.fromkeys(
    ("missing", "not-executable"),
    (
        '    except CommandUnavailableError as wrapped:\n        return _json_result(\n            VERDICT_BROKEN,\n            reason="command-unavailable",\n            command=list(spec.command),\n            detail=str(wrapped.error),\n        )\n\n',
        '    except CommandUnavailableError as wrapped:\n        return _json_result(\n            VERDICT_PASS,\n            reason="command-unavailable",\n            command=list(spec.command),\n            detail=str(wrapped.error),\n        )\n\n',
    ),
)


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
    suites = list(tree.iter("testsuite"))
    require(len(suites) == 1, "expected exactly one suite")
    suite = suites[0]
    expected_counts = {"tests": 1, "failures": int(phase == "red"), "errors": 0, "skipped": 0}
    require(
        {key: int(suite.get(key, "-1")) for key in expected_counts} == expected_counts,
        "suite totals contradict the selected outcome",
    )
    cases = list(tree.iter("testcase"))
    require(len(cases) == 1, "expected exactly one selected case")
    case = cases[0]
    require(case in list(suite), "selected case must be directly inside the suite")
    outcomes = [
        element for element in tree.iter() if element.tag in {"failure", "error", "skipped"}
    ]
    require(
        [element.tag for element in outcomes] == (["failure"] if phase == "red" else [])
        and all(element in list(case) for element in outcomes),
        "unexpected or misplaced JUnit outcomes",
    )
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
            and failure.get("message", "").startswith(("assert ", "AssertionError: assert "))
            and "FAIL_BROKEN" in (failure.text or ""),
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
            with tempfile.TemporaryDirectory(prefix="head-launch-") as private:
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
                (output / f"{label}-original.py.txt").write_bytes(original)
                (output / f"{label}-mutant.py.txt").write_bytes(target.read_bytes())
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
                (output / f"{label}-restored.py.txt").write_bytes(target.read_bytes())
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
