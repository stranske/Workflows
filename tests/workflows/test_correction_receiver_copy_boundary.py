"""Exercise the native collection step after pruning receiver-only duplicates."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RETIRED = tuple(
    f".github/scripts/verifier_correction_{name}"
    for name in ("collector.js", "profile.py", "seed.js")
)


def test_receiver_pruning_preserves_native_collection_and_source_offline_api(tmp_path):
    receiver = tmp_path / "receiver"
    source = tmp_path / "workflows"
    for destination, origin in (
        (receiver, ROOT / "templates/consumer-repo"),
        (source, ROOT),
    ):
        shutil.copytree(origin / ".github/scripts", destination / ".github/scripts")
    for path in RETIRED:
        assert not (receiver / path).exists()
        assert (source / path).is_file()

    workflow = yaml.safe_load(
        (ROOT / "templates/consumer-repo/.github/workflows/agents-verify-to-new-pr.yml").read_text()
    )
    steps = workflow["jobs"]["collect-correction"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["repository"] == "stranske/Workflows"
    assert "path" not in checkout["with"]
    assert ".github/scripts" in checkout["with"]["sparse-checkout"].splitlines()
    script = next(step["with"]["script"] for step in steps if step.get("id") == "correction")
    offline = subprocess.run(
        [
            "node",
            "-e",
            "for(const n of ['collector','seed']) require('./.github/scripts/verifier_correction_'+n)",
        ],
        cwd=source,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert offline.returncode == 0, offline.stderr
    runner = """
const fs = require('fs');
const script = JSON.parse(process.env.COLLECTION_SCRIPT);
const core = {setOutput(){},info(){},warning(){},summary:{addHeading(){return this},addRaw(){return this},write(){}}};
const context = {repo:{owner:'stranske',repo:'receiver'},runId:1,actor:'test'};
(async()=>{
  await new (Object.getPrototypeOf(async function(){}).constructor)('require','github','context','core',script)(require,{},context,core);
  console.log(fs.readFileSync('agent-metrics/verifier-followup-ledger.ndjson','utf8'));
})().catch(error=>{console.error(error);process.exitCode=1});
"""
    env = {
        **os.environ,
        "COLLECTION_SCRIPT": json.dumps(script),
        "CORRECTION_SELECTOR": "bad-json",
        "GITHUB_RUN_ATTEMPT": "1",
    }
    result = subprocess.run(
        ["node", "-e", runner], cwd=source, env=env, text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["effect_state"] == "confirmed_not_started"
    assert receipt["schema"] == "closer-correction-admission-refusal/v1"

    # Negative control: the same native entry point must fail if its actual
    # Workflows dependency is absent, even though receiver copies still exist.
    (source / ".github/scripts/verifier_correction_consumer.js").unlink()
    broken = subprocess.run(
        ["node", "-e", runner], cwd=source, env=env, text=True, capture_output=True, timeout=30
    )
    assert broken.returncode != 0
    assert "MODULE_NOT_FOUND" in broken.stderr
