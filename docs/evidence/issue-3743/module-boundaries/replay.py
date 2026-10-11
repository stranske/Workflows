"""Replay six production mutations, restoring only private source copies in finally."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CASES = (
    (
        "test_uv_option_terminator_keeps_the_selected_python_runtime",
        "_uv_python_module_probe",
        'if option == "--":\n            index += 1\n            break',
        'if option == "--":\n            index += 0\n            break',
    ),
    (
        "test_uv_module_named_python_is_not_a_nested_interpreter",
        "_uv_python_module_probe",
        'if option in {"-m", "--module"}:\n            return None',
        'if option in {"-m", "--module"}:\n            index += 1\n            continue',
    ),
    (
        "test_python_nonpytest_module_does_not_consume_trailing_pytest",
        "_python_module_pytest_probe",
        "            return None\n        if (",
        "            index += 2\n            continue\n        if (",
    ),
)
TEST = "tests/scripts/test_check_deliberate_break_module_boundaries.py"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    # Refuse existing paths before reading or mutating production sources.
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix="module-boundary-replay-") as temporary:
        replay_root = Path(temporary)
        for relative in (
            "scripts/check_deliberate_break.py",
            "templates/consumer-repo/scripts/check_deliberate_break.py",
            TEST,
        ):
            target = replay_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, target)
        for variant, prefix in (("root", ""), ("template", "templates/consumer-repo/")):
            source = replay_root / prefix / "scripts/check_deliberate_break.py"
            original = source.read_bytes()
            for test, function, before, after in CASES:
                name = f"{variant}-{test}"
                start = original.index(f"def {function}(".encode())
                end = original.index(b"\ndef ", start + 1)
                block = original[start:end]
                assert block.count(before.encode()) == 1, (name, "mutation anchor changed")
                mutated = (
                    original[:start]
                    + block.replace(before.encode(), after.encode())
                    + original[end:]
                )
                row = {
                    "name": name,
                    "source": str(source.relative_to(replay_root)),
                    "original_sha256": digest(original),
                    "mutation_sha256": digest(mutated),
                    "test_sha256": digest((root / TEST).read_bytes()),
                    "cwd": str(replay_root),
                }
                try:
                    source.write_bytes(mutated)
                    for phase in ("red", "green"):
                        if phase == "green":
                            source.write_bytes(original)
                        argv = [
                            sys.executable,
                            "-m",
                            "pytest",
                            f"{TEST}::{test}[{variant}]",
                            "-q",
                            "-o",
                            "addopts=",
                            f"--junitxml={args.output / (name + '-' + phase + '.xml')}",
                        ]
                        # argv uses the running interpreter and a constant, checked-in test node.
                        # No shell is used; output paths are individual argv operands.
                        run = subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
                            argv, cwd=replay_root, capture_output=True, timeout=60
                        )
                        (args.output / f"{name}-{phase}.stdout").write_bytes(run.stdout)
                        (args.output / f"{name}-{phase}.stderr").write_bytes(run.stderr)
                        row[phase] = {"argv": argv, "exit": run.returncode}
                finally:
                    source.write_bytes(original)
                    row["restored_sha256"] = digest(source.read_bytes())
                    results.append(row)
                    (args.output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
                assert row["red"]["exit"] == 1, row
                assert row["green"]["exit"] == 0, row
                assert row["original_sha256"] == row["restored_sha256"], row
    print(json.dumps({"cases": len(results), "all_red_then_green": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
