"""Replay every runtime-probe mutation into a fresh, immutable output directory."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, detail):
    if not condition:
        raise RuntimeError(detail)


def validate_junit(text, node, phase):
    """Require the selected test's assertion failure or pass, never an error/skip."""
    report = ElementTree.fromstring(text)
    suites = list(report.iter("testsuite"))
    require(len(suites) == 1, "expected exactly one JUnit suite")
    suite = suites[0]
    counts = {key: int(suite.get(key, "-1")) for key in ("tests", "failures", "errors", "skipped")}
    expected = {"tests": 1, "failures": int(phase == "red"), "errors": 0, "skipped": 0}
    require(counts == expected, (node, phase, counts))
    cases = list(suite.iter("testcase"))
    require(len(cases) == 1 and cases[0].get("name") == node.rsplit("::", 1)[1], node)
    module = Path(node.split("::", 1)[0]).with_suffix("").as_posix().replace("/", ".")
    require(cases[0].get("classname") == module, (node, cases[0].get("classname")))
    outcomes = [child.tag for child in cases[0] if child.tag in {"failure", "error", "skipped"}]
    require(outcomes == (["failure"] if phase == "red" else []), (node, phase, outcomes))
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
                require(text.count(before) == 1, (name, text.count(before)))
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
                        # Keep user-selected output paths out of child argv.
                        with tempfile.TemporaryDirectory(
                            prefix="runtime-probe-junit-"
                        ) as phase_dir:
                            junit = Path(phase_dir) / "pytest.xml"
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
                                argv,
                                cwd=root,
                                text=True,
                                encoding="utf-8",
                                capture_output=True,
                                timeout=60,
                            )
                            if junit.exists():
                                (output / f"{len(records):02}-{phase}.xml").write_bytes(
                                    junit.read_bytes()
                                )
                            stem = output / f"{len(records):02}-{phase}"
                            stem.with_suffix(".stdout").write_text(result.stdout, encoding="utf-8")
                            stem.with_suffix(".stderr").write_text(result.stderr, encoding="utf-8")
                            record[phase] = {
                                "argv": argv,
                                "cwd": str(root),
                                "exit": result.returncode,
                                "stdout": result.stdout,
                                "stderr": result.stderr,
                                "junit": (
                                    junit.read_text(encoding="utf-8") if junit.exists() else None
                                ),
                            }
                            print(label, name, parameter, phase, result.returncode, flush=True)
                            require(result.returncode == (1 if phase == "red" else 0), record)
                            record[phase]["junit_counts"] = validate_junit(
                                record[phase]["junit"], node, phase
                            )
                finally:
                    source.write_bytes(original)
                    record["restored_sha256"] = digest(source.read_bytes())
                    require(record["restored_sha256"] == record["source_sha256"], record)
                    records.append(record)
                    (output / "controls.json").write_text(json.dumps(records, indent=2) + "\n")
    finally:
        for source, original in originals.items():
            source.write_bytes(original)
    require(len(records) == 14, "Incomplete mutation replay")


if __name__ == "__main__":
    main()
