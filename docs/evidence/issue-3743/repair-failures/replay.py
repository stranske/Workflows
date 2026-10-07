"""Replay six production mutations in a private tree; never mutate caller files."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TEST = "tests/scripts/test_check_deliberate_break_repair_failures.py"
HELPER = "scripts/check_deliberate_break.py"
MUTATIONS = {
    "probe": (
        "    except OSError as exc:\n"
        "        raise CommandUnavailableError(exc) from exc\n"
        "    if not probe_succeeded:",
        "    except OSError:\n        raise\n    if not probe_succeeded:",
    ),
    "rerun": (
        "        return _run(command, cwd)\n"
        "    except OSError as exc:\n"
        "        raise CommandUnavailableError(exc) from exc",
        "        return _run(command, cwd)\n    except OSError:\n        raise",
    ),
    "base": (
        "    except ValueError as exc:\n"
        "        return _json_result(\n"
        "            VERDICT_BROKEN,\n"
        '            reason="archive-extract-failed",\n'
        "            detail=str(exc),\n"
        "        )\n"
        "    except RuntimeDependencyError as wrapped:\n"
        "        return _runtime_dependency_error_result(wrapped.error)",
        "    except ValueError as exc:\n"
        "        return _json_result(\n"
        "            VERDICT_BROKEN,\n"
        '            reason="archive-extract-failed",\n'
        "            detail=str(exc),\n"
        "        )\n"
        "    except RuntimeDependencyError as wrapped:\n"
        '        return _json_result(VERDICT_PASS, reason="mutated-base-repair")',
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
    identities = {path: digest((root / path).read_bytes()) for path in [TEST, HELPER]}
    controls = []
    with tempfile.TemporaryDirectory(prefix="repair-failures-proof-") as temporary:
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
                suffix = f"[{copy}]" if kind == "base" else f"[{copy}-{kind}]"
                name = (
                    "test_base_dependency_failure_keeps_its_cause_and_cleans_real_archive"
                    if kind == "base"
                    else "test_repaired_runtime_preserves_a_later_real_launch_failure"
                )
                node = f"{TEST}::{name}{suffix}"
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
    assert len(controls) == 6
    assert identities == {path: digest((root / path).read_bytes()) for path in identities}
    (output / "controls.json").write_text(
        json.dumps({"caller_identity": identities, "controls": controls}, indent=2),
        encoding="utf-8",
    )
    print("6 named production mutations RED; 6 exact restorations GREEN; caller bytes unchanged")


if __name__ == "__main__":
    main()
