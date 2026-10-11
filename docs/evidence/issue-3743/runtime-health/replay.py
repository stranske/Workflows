"""Replay eight production mutations, restoring only private source copies in finally."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CASES = (
    (
        "missing",
        "except metadata.PackageNotFoundError:\n        return True",
        "except metadata.PackageNotFoundError:\n        return False",
    ),
    (
        "stale",
        "if not _supported_pyyaml_version(installed_version):\n        return True",
        "if not _supported_pyyaml_version(installed_version):\n        return False",
    ),
    ("broken", "except Exception:\n        return True", "except Exception:\n        return False"),
    ("healthy", "    return False", "    return True"),
)
TEST = "tests/scripts/test_check_deliberate_break_runtime_health.py"
FUNCTION = "_pyyaml_runtime_needs_repair"
TEST_FUNCTION = "test_active_runtime_health_requires_distribution_version_and_real_import"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    root = Path(__file__).resolve().parents[4]
    # Refuse existing paths before reading or mutating production sources.
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix="runtime-health-replay-") as temporary:
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
            for health, before, after in CASES:
                test, function = TEST_FUNCTION, FUNCTION
                name = f"{variant}-{health}"
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
                            f"{TEST}::{test}[{variant}-{health}]",
                            "-q",
                            "-o",
                            "addopts=",
                        ]
                        # pytest parses this environment option with shlex. Keep
                        # user-selected report paths out of executable argv.
                        env = os.environ.copy()
                        env["PYTEST_ADDOPTS"] = shlex.join(
                            [f"--junitxml={args.output / (name + '-' + phase + '.xml')}"]
                        )
                        run = subprocess.run(
                            argv,
                            cwd=replay_root,
                            env=env,
                            capture_output=True,
                            timeout=60,
                            check=False,
                        )
                        (args.output / f"{name}-{phase}.stdout").write_bytes(run.stdout)
                        (args.output / f"{name}-{phase}.stderr").write_bytes(run.stderr)
                        row[phase] = {
                            "argv": argv,
                            "env": {"PYTEST_ADDOPTS": env["PYTEST_ADDOPTS"]},
                            "exit": run.returncode,
                        }
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
