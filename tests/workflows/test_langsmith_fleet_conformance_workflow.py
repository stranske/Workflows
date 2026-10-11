import subprocess
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/maint-81-langsmith-fleet-conformance.yml")
HELPER = Path(".github/scripts/langsmith-fleet-artifacts.js").resolve()


def download_script():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["conformance"]["steps"]
    return next(
        s["with"]["script"] for s in steps if s["name"] == "Download latest fleet artifacts"
    )


def test_production_download_handles_large_repository_without_inventory_scan():
    # Execute the actual authored workflow with >30k unrelated artifacts.
    # Reintroducing the old unfiltered paginate(per_page=100) throws a 500.
    harness = r"""
const assert = require('node:assert/strict');
const calls = [], writes = [];
const registry = {repos:[{repo:'o/r',artifact_name:'langsmith-fleet.ndjson'}]};
const github = {paginate:async()=>{throw Object.assign(new Error('large inventory 500'),{status:500});},
 rest:{actions:{listArtifactsForRepo:async p=>{
 calls.push(p); assert.equal(p.name,'langsmith-fleet.ndjson');
 return {data:{total_count:1,artifacts:[{id:7,name:p.name,created_at:'2026-10-11',expired:false}]}};
 },downloadArtifact:async p=>({data:Buffer.from('zip')}),getWorkflowRun:async()=>{throw Error('unexpected');}}}};
const realRequire = require;
const fakeRequire = name => name==='fs' ? {
 readFileSync:()=>JSON.stringify(registry),mkdirSync:()=>{},writeFileSync:(p,b)=>writes.push(p)
} : name.endsWith('github-api-with-retry.js') ? {withRetry:fn=>fn()} :
 name.endsWith('langsmith-fleet-artifacts.js') ? realRequire(process.env.HELPER) : realRequire(name);
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
(async()=>{await new AsyncFunction('github','core','require',process.env.SCRIPT)(github,{warning:()=>{}},fakeRequire);
 assert.equal(calls.length,1); assert.equal(writes.length,1); console.log('production large-inventory download PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    import os

    proc = subprocess.run(
        ["node", "-e", harness],
        env={**os.environ, "SCRIPT": download_script(), "HELPER": str(HELPER)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_conformance_skips_direct_evidence_entries():
    source = WORKFLOW.read_text()
    assert "(entry.evidence_mode || 'artifact') !== 'artifact'" in source
    assert 'select((.evidence_mode // "artifact") == "artifact")' in source
    assert 'select(.status == "missing" or .status == "invalid" or .status == "stale")' in source


def test_routine_observability_retention_is_bounded():
    for name in [
        "maint-80-langsmith-metrics-dashboard.yml",
        "maint-81-langsmith-fleet-conformance.yml",
        "health-84-langsmith-observability.yml",
    ]:
        workflow = yaml.safe_load((WORKFLOW.parent / name).read_text())
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if "actions/upload-artifact@" in step.get("uses", ""):
                    assert step["with"]["retention-days"] == 30
