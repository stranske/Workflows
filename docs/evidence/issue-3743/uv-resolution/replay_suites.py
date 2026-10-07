"""Replay the matched suites from this checkout with portable output paths."""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

SUITE = [
    "test_check_deliberate_break.py",
    "test_check_deliberate_break_archive.py",
    "test_check_deliberate_break_launch_boundaries.py",
    "test_check_deliberate_break_runtime_probes.py",
    "test_launch_mutation_driver.py",
    "test_runtime_probe_replay.py",
    "test_check_deliberate_break_repair_failures.py",
]
NEW = "test_check_deliberate_break_uv_resolution.py"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    selection = json.loads(Path(__file__).with_name("selection.json").read_text())
    for relative, expected in selection["suite_inputs"].items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"suite input drift: {relative}")
    exits = []
    for phase in ("baseline", "candidate"):
        tests = SUITE + ([NEW] if phase == "candidate" else [])
        argv = [
            sys.executable,
            "-m",
            "pytest",
            *(f"tests/scripts/{name}" for name in tests),
            "-q",
            "-o",
            "addopts=",
            "-m",
            "not slow",
            "--cov=scripts.check_deliberate_break",
            "--cov-branch",
        ]
        env = os.environ.copy()
        env["COVERAGE_FILE"] = str(output / f".coverage-{phase}")
        # Keep user-selected artifact paths out of the executable argument list.
        # pytest parses this value with shlex; quote each complete option.
        env["PYTEST_ADDOPTS"] = shlex.join(
            [
                f"--cov-report=json:{output / phase}.json",
                f"--junitxml={output / phase}.xml",
                "--cov-report=term-missing",
            ]
        )
        (output / f"{phase}-command.json").write_text(
            json.dumps(
                {
                    "argv": argv,
                    "cwd": str(root),
                    "env": {name: env[name] for name in ("COVERAGE_FILE", "PYTEST_ADDOPTS")},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with (output / f"{phase}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(
                argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600
            )
        exits.append(result.returncode)
        (output / f"{phase}-exit.json").write_text(
            json.dumps({"exit": result.returncode}), encoding="utf-8"
        )
        print(f"{phase}: exit {result.returncode}", flush=True)
    raise SystemExit(0 if exits == [0, 0] else 1)


if __name__ == "__main__":
    main()
