"""Reproduce eight assertion RED/restored GREEN pairs in a private source copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.parsers import expat

TEST = "tests/scripts/test_check_deliberate_break_shebang_rejection.py"
HELPER = "scripts/check_deliberate_break.py"
MUTATIONS = {
    "test_empty_pytest_launcher_has_no_probe": (
        "    except (OSError, UnicodeError, IndexError):\n        return None\n",
        '    except (OSError, UnicodeError, IndexError):\n        return (sys.executable, "-c", PYYAML_PROBE_CODE)\n',
    ),
    "test_missing_shebang_has_no_probe": (
        '    if not shebang.startswith("#!"):\n        return None\n',
        '    if not shebang.startswith("#!"):\n        return (sys.executable, "-c", PYYAML_PROBE_CODE)\n',
    ),
    "test_unclosed_shebang_quote_has_no_probe": (
        "    except ValueError:\n        return None\n    if not launcher:\n",
        '    except ValueError:\n        return (sys.executable, "-c", PYYAML_PROBE_CODE)\n    if not launcher:\n',
    ),
    "test_unresolved_env_python_has_no_probe": (
        "        if not resolved:\n            return None\n",
        '        if not resolved:\n            return (sys.executable, "-c", PYYAML_PROBE_CODE)\n',
    ),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_junit(path: Path) -> ET.Element:
    """Read JUnit without dependencies, rejecting DTDs and entity declarations."""
    data = path.read_bytes()
    parser = expat.ParserCreate()

    def reject_declaration(*args):
        raise ValueError("JUnit must not contain DTDs or entity declarations")

    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    parser.Parse(data, True)
    return ET.fromstring(data)


def run_node(checkout: Path, output: Path, node: str, phase: str) -> dict:
    junit = output / f"{phase}.xml"
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
    result = subprocess.run(argv, cwd=checkout, capture_output=True, text=True, timeout=60)
    (output / f"{phase}.stdout").write_text(result.stdout, encoding="utf-8")
    (output / f"{phase}.stderr").write_text(result.stderr, encoding="utf-8")
    cases = list(parse_junit(junit).iter("testcase"))
    failures = [failure for case in cases for failure in case.findall("failure")]
    errors = [error for case in cases for error in case.findall("error")]
    skips = [skip for case in cases for skip in case.findall("skipped")]
    assert len(cases) == 1 and not errors and not skips, result.stdout + result.stderr
    assert cases[0].get("name") == node.split("::", 1)[1]
    assert cases[0].get("classname") == node.split("::", 1)[0][:-3].replace("/", ".")
    if phase == "red":
        assert result.returncode == 1 and len(failures) == 1
        assert "AssertionError" in "".join(failures[0].itertext())
    else:
        assert result.returncode == 0 and not failures
    record = {"argv": argv, "cwd": str(checkout), "exit": result.returncode, "node": node}
    (output / f"{phase}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def replay(root: Path, output: Path) -> dict:
    # Claim the output before creating a checkout or touching any source bytes.
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / "inputs"
    inputs.mkdir()
    for relative in [HELPER, "templates/consumer-repo/" + HELPER, TEST]:
        destination = inputs / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, destination)
    shutil.copyfile(Path(__file__), inputs / "replay.py")
    records = []
    with tempfile.TemporaryDirectory(prefix="shebang-rejection-proof-") as temporary:
        checkout = Path(temporary)
        shutil.copytree(inputs, checkout, dirs_exist_ok=True)
        for prefix, case_id in [("", "root"), ("templates/consumer-repo/", "template")]:
            source = checkout / prefix / HELPER
            original = source.read_bytes()
            for name, (needle, replacement) in MUTATIONS.items():
                case_output = output / f"{case_id}-{name}"
                case_output.mkdir()
                text = original.decode("utf-8")
                assert text.count(needle) == 1, "mutation must match exactly once"
                mutant = text.replace(needle, replacement, 1).encode("utf-8")
                node = f"{TEST}::{name}[{case_id}]"
                (case_output / "original.py").write_bytes(original)
                (case_output / "mutant.py").write_bytes(mutant)
                source.write_bytes(mutant)
                try:
                    red = run_node(checkout, case_output, node, "red")
                finally:
                    source.write_bytes(original)
                restored = source.read_bytes()
                assert restored == original
                (case_output / "restored.py").write_bytes(restored)
                green = run_node(checkout, case_output, node, "green")
                records.append(
                    {
                        "node": node,
                        "source": prefix + HELPER,
                        "original_sha256": digest(original),
                        "mutant_sha256": digest(mutant),
                        "restored_sha256": digest(restored),
                        "red": red,
                        "green": green,
                    }
                )
    summary = {"pairs": records, "pair_count": len(records)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    summary = replay(root, args.output.resolve())
    print(json.dumps({"pair_count": summary["pair_count"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
