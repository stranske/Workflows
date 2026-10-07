"""Replay every runtime-probe mutation into a fresh, immutable output directory."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_junit(text, node, phase):
    """Require the selected test's assertion failure or pass, never an error/skip."""
    report = ElementTree.fromstring(text)
    suites = list(report.iter("testsuite"))
    assert len(suites) == 1, "expected exactly one JUnit suite"
    suite = suites[0]
    counts = {key: int(suite.get(key, "-1")) for key in ("tests", "failures", "errors", "skipped")}
    expected = {"tests": 1, "failures": int(phase == "red"), "errors": 0, "skipped": 0}
    assert counts == expected, (node, phase, counts)
    cases = list(suite.iter("testcase"))
    assert len(cases) == 1 and cases[0].get("name") == node.rsplit("::", 1)[1], node
    outcomes = [child.tag for child in cases[0] if child.tag in {"failure", "error", "skipped"}]
    assert outcomes == (["failure"] if phase == "red" else []), (node, phase, outcomes)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[4]
    test = "tests/scripts/test_check_deliberate_break_runtime_probes.py"
    decision = "return probe.returncode == 0 and PYYAML_PROBE_SENTINEL in probe.stdout"
    cases = [
        (
            "test_real_import_probe_requires_success_and_its_sentinel",
            "healthy",
            decision,
            "return False",
        ),
        (
            "test_real_import_probe_requires_success_and_its_sentinel",
            "zero-without-sentinel",
            decision,
            "return probe.returncode == 0",
        ),
        (
            "test_real_import_probe_requires_success_and_its_sentinel",
            "nonzero",
            decision,
            "return PYYAML_PROBE_SENTINEL in probe.stdout",
        ),
        (
            "test_unrecognized_runtime_probe_never_launches_custom_command",
            "",
            "if probe_command is None:\n        return False",
            "if probe_command is None:\n        _run(command, cwd)\n        return False",
        ),
        (
            "test_real_missing_probe_executable_preserves_launch_cause",
            "custom",
            "probe = _run(probe_command, cwd)\n            except OSError as exc:\n                raise CommandUnavailableError(exc) from exc",
            "probe = _run(probe_command, cwd)\n            except OSError as exc:\n                raise RuntimeDependencyError(exc) from exc",
        ),
        (
            "test_real_missing_probe_executable_preserves_launch_cause",
            "managed",
            "except OSError as exc:\n                raise CommandUnavailableError(exc) from exc\n        elif probe_command",
            "except OSError as exc:\n                raise RuntimeDependencyError(exc) from exc\n        elif probe_command",
        ),
        (
            "test_repair_failure_preserves_dependency_error_without_rerunning",
            "",
            "raise RuntimeDependencyError(exc) from exc",
            'raise RuntimeDependencyError(ImportError("lost repair cause")) from exc',
        ),
    ]
    records = []
    originals = {}
    try:
        for prefix, label in [("", "root"), ("templates/consumer-repo/", "template")]:
            source = root / prefix / "scripts/check_deliberate_break.py"
            original = source.read_bytes()
            originals[source] = original
            for name, parameter, before, after in cases:
                text = original.decode()
                assert text.count(before) == 1, (name, text.count(before))
                mutated = text.replace(before, after, 1).encode()
                node = f"{test}::{name}[{label}{'-' + parameter if parameter else ''}]"
                record = {
                    "source": str(source.relative_to(root)),
                    "node": node,
                    "source_sha256": digest(original),
                    "mutation_sha256": digest(mutated),
                    "test_sha256": digest((root / test).read_bytes()),
                    "before": before,
                    "after": after,
                }
                try:
                    for phase, data in [("red", mutated), ("green", original)]:
                        source.write_bytes(data)
                        junit = output / f"{len(records):02}-{phase}.xml"
                        argv = [
                            sys.executable,
                            "-m",
                            "pytest",
                            node,
                            "-q",
                            "-o",
                            "addopts=",
                            "-m",
                            "not slow",
                            f"--junitxml={junit}",
                        ]
                        result = subprocess.run(
                            argv, cwd=root, text=True, capture_output=True, timeout=60
                        )
                        stem = output / f"{len(records):02}-{phase}"
                        stem.with_suffix(".stdout").write_text(result.stdout)
                        stem.with_suffix(".stderr").write_text(result.stderr)
                        record[phase] = {
                            "argv": argv,
                            "cwd": str(root),
                            "exit": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "junit": junit.read_text() if junit.exists() else None,
                        }
                        print(label, name, parameter, phase, result.returncode, flush=True)
                        assert result.returncode == (1 if phase == "red" else 0), record
                        record[phase]["junit_counts"] = validate_junit(
                            record[phase]["junit"], node, phase
                        )
                finally:
                    source.write_bytes(original)
                    record["restored_sha256"] = digest(source.read_bytes())
                    assert record["restored_sha256"] == record["source_sha256"]
                    records.append(record)
                    (output / "controls.json").write_text(json.dumps(records, indent=2) + "\n")
    finally:
        for source, original in originals.items():
            source.write_bytes(original)
    assert len(records) == 14


if __name__ == "__main__":
    main()
