import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from defusedxml import ElementTree as ET

root = Path.cwd()
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
out = args.output.resolve()
if out.is_relative_to(root):
    raise SystemExit("Keep fresh proof outside the repository")
out.mkdir(parents=True, exist_ok=False)
paths = [
    Path(".github/workflows/agents-keepalive-loop-reporter.yml"),
    Path("templates/consumer-repo/.github/workflows/agents-keepalive-loop-reporter.yml"),
]
fixed = {p: p.read_bytes() for p in paths}
block = """              // An unverified failed run still needs an attributed visible failure.
              // A targetless classifier skip cannot waive the reporter's source contract.
              if (result.status === 'skip' && result.reason ===
                  'unassociated run has no verified dispatch classification') {
                throw new Error(result.reason);
              }
"""


def run(phase):
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/workflows/test_keepalive_reporter_unresolved.py::test_unassociated_workflow_run_reports_attributed_failure_before_failing",
        "-q",
        "-o",
        "addopts=",
        f'--junitxml={out/(phase+".xml")}',
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / (phase + ".log")).write_bytes(proc.stdout)
    cases = list(ET.parse(out / (phase + ".xml")).iter("testcase"))
    return {
        "phase": phase,
        "argv": cmd,
        "exit": proc.returncode,
        "cases": len(cases),
        "failures": sum(len(c.findall("failure")) for c in cases),
        "errors": sum(len(c.findall("error")) for c in cases),
        "skips": sum(len(c.findall("skipped")) for c in cases),
    }


try:
    for p, b in fixed.items():
        assert b.decode().count(block) == 1
        p.write_text(b.decode().replace(block, ""))
    red = run("production-skip-red")
finally:
    for p, b in fixed.items():
        p.write_bytes(b)
green = run("exact-restoration-green")
assert all(p.read_bytes() == b for p, b in fixed.items())
assert (red["exit"], red["cases"], red["failures"], red["errors"], red["skips"]) == (
    1,
    6,
    6,
    0,
    0,
), red
assert (green["exit"], green["cases"], green["failures"], green["errors"], green["skips"]) == (
    0,
    6,
    0,
    0,
    0,
), green
receipt = {
    "scope": "actual root/consumer workflow guard removed; classifier unchanged; six failed/cancelled/timed-out runs",
    "fixed_sha256": {str(p): hashlib.sha256(b).hexdigest() for p, b in fixed.items()},
    "byte_identical_restoration": True,
    "results": [red, green],
}
(out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt))
