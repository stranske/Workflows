"""Mutate actual production YAML, require behavioral RED, restore exact bytes."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path(__file__).resolve().parent
TEMPLATE = "templates/consumer-repo/.github/workflows/agents-verifier.yml"
SOURCE = ".github/workflows/agents-verifier.yml"
REUSABLE = ".github/workflows/reusable-agents-verifier.yml"
TEST = "tests/workflows/test_verifier_caller_security.py"
MUTATIONS = [
    (
        "secrets",
        TEMPLATE,
        "    secrets:\n"
        "      CODEX_AUTH_JSON: ${{ secrets.CODEX_AUTH_JSON }}\n"
        "      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}\n"
        "      CLAUDE_API_STRANSKE: ${{ secrets.CLAUDE_API_STRANSKE }}\n"
        "      LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}\n"
        "      workflows_app_id: ${{ secrets.WORKFLOWS_APP_ID }}\n"
        "      workflows_app_private_key: ${{ secrets.WORKFLOWS_APP_PRIVATE_KEY }}",
        "    secrets: inherit",
        "secret_allowlist",
    ),
    (
        "permissions",
        SOURCE,
        "permissions: {}",
        "permissions:\n  issues: write",
        "job_scoped_permissions",
    ),
    (
        "checkout",
        TEMPLATE,
        "ref: ${{ github.sha }}",
        "ref: ${{ github.event.pull_request.head.sha }}",
        "checkout_executes_trusted",
    ),
    (
        "merged-gate",
        TEMPLATE,
        "github.event.pull_request.merged == true",
        "github.event.pull_request.merged != true",
        "trigger_gate_runs_before",
    ),
    (
        "shell",
        TEMPLATE,
        "run: printf 'Skipped - %s\\n' \"$FINGERPRINT_REASON\"",
        'run: echo "Skipped - ${{ steps.fingerprint.outputs.reason }}"',
        "fingerprint_shell",
    ),
    (
        "credentials",
        REUSABLE,
        "persist-credentials: false",
        "persist-credentials: true",
        "checkout_executes_trusted",
    ),
]


def run(name, selector):
    command = [
        sys.executable,
        "-m",
        "pytest",
        TEST,
        "-k",
        selector,
        "-q",
        "-o",
        "addopts=",
        f"--junitxml={EVIDENCE / ('verifier-caller-security-' + name + '.xml')}",
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (EVIDENCE / f"verifier-caller-security-{name}.txt").write_text(result.stdout + result.stderr)
    return {
        "command": command,
        "exit_code": result.returncode,
        "executed_failure": " failed" in result.stdout and "ERROR collecting" not in result.stdout,
    }


receipts = []
for name, filename, original, broken, selector in MUTATIONS:
    path = ROOT / filename
    before = path.read_bytes()
    assert original in before.decode(), name
    try:
        path.write_text(before.decode().replace(original, broken, 1))
        mutated = hashlib.sha256(path.read_bytes()).hexdigest()
        red = run(name + "-red", selector)
        assert red["exit_code"] == 1 and red["executed_failure"], red
    finally:
        path.write_bytes(before)
    assert path.read_bytes() == before
    green = run(name + "-restored-green", selector)
    assert green["exit_code"] == 0, green
    receipts.append(
        {
            "name": name,
            "production_path": filename,
            "before_sha256": hashlib.sha256(before).hexdigest(),
            "mutated_sha256": mutated,
            "restored_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "red": red,
            "green": green,
        }
    )

(EVIDENCE / "verifier-caller-security-red-green.json").write_text(
    json.dumps(receipts, indent=2) + "\n"
)
print("Six production YAML mutations: executed RED; byte-identical restoration GREEN.")
