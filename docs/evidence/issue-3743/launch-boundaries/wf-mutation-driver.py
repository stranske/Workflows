import argparse
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description="Rerun the ten launch-boundary source mutations.")
parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "revalidation")
args = parser.parse_args()
repo = args.repo.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
test = "tests/scripts/test_check_deliberate_break_launch_boundaries.py"
mutations = [
    (
        "pythonpath",
        '            pythonpath = pythonpath + os.pathsep + env["PYTHONPATH"]',
        "            pythonpath = pythonpath",
        "test_real_command_preserves_existing_pythonpath",
    ),
    (
        "missing-test",
        "    if not test_path.is_file():",
        "    if False:",
        "test_missing_test_never_launches_the_command",
    ),
    (
        "missing-executable",
        "        raise CommandUnavailableError(exc) from exc",
        "        raise exc",
        "test_real_missing_executable_is_wrapped_with_its_cause",
    ),
    (
        "head-timeout",
        '            reason="command-timeout",',
        '            reason="head-test-failed",',
        "test_real_head_timeout_stops_before_base_archive",
    ),
    (
        "base-timeout",
        '            reason="command-timeout",',
        '            reason="base-test-failed",',
        "test_real_base_timeout_is_broken_and_cleans_private_archive",
    ),
]
receipts = []
for prefix in ["", "templates/consumer-repo/"]:
    source = repo / prefix / "scripts/check_deliberate_break.py"
    original = source.read_bytes()
    side = "template" if prefix else "root"
    for name, old, new, node in mutations:
        text = original.decode()
        if name == "pythonpath":
            # Exact source indentation is eight spaces inside the environment condition.
            old = old.lstrip()
            new = new.lstrip()
            assert old in text
            changed = text.replace(old, new, 1)
        elif name == "base-timeout":
            split = text.index("    try:\n        with tempfile.TemporaryDirectory")
            a, b = text[:split], text[split:]
            assert old in b
            changed = a + b.replace(old, new, 1)
        else:
            assert old in text
            changed = text.replace(old, new, 1)
        argv = [
            "python3",
            "-m",
            "pytest",
            test + "::" + node + "[" + side + "]",
            "-q",
            "-o",
            "addopts=",
            "-m",
            "not slow",
        ]
        try:
            source.write_text(changed)
            red = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
            with gzip.open(out / f"wf-{side}-{name}-red.log.gz", "wt") as log:
                log.write(red.stdout + red.stderr)
            assert red.returncode == 1, (side, name, red.returncode, red.stdout, red.stderr)
        finally:
            source.write_bytes(original)
        assert source.read_bytes() == original
        green = subprocess.run(argv, cwd=repo, capture_output=True, text=True)
        with gzip.open(out / f"wf-{side}-{name}-green.log.gz", "wt") as log:
            log.write(green.stdout + green.stderr)
        assert green.returncode == 0, (side, name, green.stdout, green.stderr)
        receipts.append(
            {
                "side": side,
                "case": node,
                "red_exit": red.returncode,
                "green_exit": green.returncode,
                "argv": argv,
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "mutant_sha256": hashlib.sha256(changed.encode()).hexdigest(),
                "restored_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "test_sha256": hashlib.sha256((repo / test).read_bytes()).hexdigest(),
                "restored_byte_identical": True,
            }
        )
(out / "wf-mutations.json").write_text(json.dumps(receipts, indent=2) + "\n")
print(
    "Ten distinct named root/template cases discriminated real source mutations; all exact restorations GREEN"
)
