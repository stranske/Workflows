"""Exercise fresh seal metadata across the runner's per-action event reset."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATES = [
    ROOT / ".github/workflows/pr-00-gate.yml",
    ROOT / "templates/consumer-repo/.github/workflows/pr-00-gate.yml",
]


@pytest.mark.parametrize("gate", GATES)
@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("fresh", 0),
        ("unsealed", 9),
        ("missing", 9),
        ("head", 1),
        ("repo", 1),
        ("number", 1),
        ("malformed", 1),
        ("null_repo", 9),
        ("resolved_null_repo", 1),
        ("null_original_repo", 1),
    ],
)
def test_summary_refresh_and_helper_share_actual_runner_action(
    tmp_path: Path, gate: Path, change: str, expected: int
) -> None:
    workflow = yaml.safe_load(gate.read_text(encoding="utf-8"))
    job = workflow["jobs"]["summary"]
    assert "resolve-pr" in job["needs"]
    assert job["env"]["GATE_PR_JSON"] == "${{ needs.resolve-pr.outputs.pull_request }}"
    step = next(s for s in job["steps"] if "gate_summary.py" in str(s.get("run", "")))
    sha = "a" * 40
    record = {
        "schema": "sync-pr-delivery-record/v1",
        "delivery_state": "sealed",
        "sealed_head_sha": sha,
        "repository": "stranske/test",
        "lease_expires_at": "2099-01-01T00:00:00+00:00",
    }
    pr = {
        "number": 7,
        "head": {
            "ref": "sync/workflows-delivery",
            "sha": sha,
            "repo": {"full_name": "stranske/test"},
        },
        "base": {"repo": {"full_name": "stranske/test"}},
        "body": "<!-- sync-pr-delivery-record:v1 " + json.dumps(record) + " -->",
    }
    if change in {"null_repo", "null_original_repo"}:
        pr["head"]["repo"] = None
    # GitHub restores this original payload immediately before the summary action.
    # A previous github-script hydration cannot change this reset boundary.
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": dict(pr, body=pr["body"].replace(sha, "b" * 40))}))
    if change == "unsealed":
        pr["body"] = pr["body"].replace('"sealed"', '"staging"')
    elif change == "head":
        pr["head"]["sha"] = "c" * 40
    elif change == "repo":
        pr["head"]["repo"]["full_name"] = "stranske/foreign"
    elif change == "number":
        pr["number"] = 8
    if change == "resolved_null_repo":
        pr["head"]["repo"] = None
    elif change == "null_original_repo":
        pr["head"]["repo"] = {"full_name": "stranske/test"}
    raw = "null" if change == "missing" else "{" if change == "malformed" else json.dumps(pr)
    helper = ROOT / ".github/scripts/gate_summary.py"
    probe = (
        "import importlib.util,sys,os,pathlib; "
        f"s=importlib.util.spec_from_file_location('boundary_summary',{str(helper)!r}); "
        "m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); "
        "sys.exit(0 if m._delivery_seal_from_event("
        "pathlib.Path(os.environ['GITHUB_EVENT_PATH']))[1] else 9)"
    )
    command = step["run"].replace(
        "python .github/scripts/gate_summary.py",
        shlex.quote(sys.executable) + " -c " + shlex.quote(probe),
    )
    result = subprocess.run(
        ["bash", "-e", "-c", command],
        capture_output=True,
        text=True,
        env={**os.environ, "GITHUB_EVENT_PATH": str(event), "GATE_PR_JSON": raw},
        check=False,
    )
    assert result.returncode == expected, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Gate expression replay requires Node")
@pytest.mark.parametrize(
    ("selected", "package", "old_quality", "docs_guard", "expected"),
    [
        ("false", "skipped", "skipped", "success", "success"),
        ("false", "failure", "skipped", "success", "success"),
        ("true", "success", "skipped", "success", "success"),
        ("true", "failure", "skipped", "success", "failure"),
        ("true", "cancelled", "skipped", "success", "pending"),
        ("true", "skipped", "skipped", "success", "failure"),
        ("true", "success", "failure", "success", "failure"),
        ("true", "cancelled", "skipped", "failure", "failure"),
    ],
)
def test_baseline_kit_uses_the_existing_required_gate_verdict(
    tmp_path: Path, selected: str, package: str, old_quality: str, docs_guard: str, expected: str
) -> None:
    workflow = yaml.safe_load(GATES[0].read_text(encoding="utf-8"))
    job = workflow["jobs"]["summary"]
    assert "packages-app-baseline-kit" in job["needs"]
    step = next(step for step in job["steps"] if step.get("id") == "summarize")
    keys = ("DOC_ONLY", "RUN_CORE", "PYTHON_REQUIRED", "TEST_QUALITY_RESULT")
    expressions = {key: step["env"][key].strip()[3:-2].strip() for key in keys}
    needs = {
        "detect": {
            "outputs": {
                "doc_only": "true",
                "run_core": "false",
                "app_baseline_kit_required": selected,
            }
        },
        "packages-app-baseline-kit": {"result": package},
        "acceptance-criteria-label": {"result": "skipped"},
        "test-quality": {"result": old_quality},
    }
    # This narrow expression subset uses only string comparisons and short-circuit logic.
    expression_replay = r"""
      const { needs, expressions } = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
      const results = Object.entries(expressions).map(([key, text]) => {
        const expression = text.replace(/needs\.([\w-]+)/g, (_, job) => 'needs[' + JSON.stringify(job) + ']');
        if (!/^[\w"' .()\[\]|!=&\s-]+$/.test(expression)) throw Error(expression);
        return [key, String(new Function('needs', 'return (' + expression + ')')(needs))];
      });
      process.stdout.write(JSON.stringify(Object.fromEntries(results)));
    """
    resolved = json.loads(
        subprocess.check_output(
            ["node", "-e", expression_replay],
            input=json.dumps({"needs": needs, "expressions": expressions}),
            text=True,
        )
    )
    assert resolved["DOC_ONLY"] == ("false" if selected == "true" else "true")
    assert resolved["PYTHON_REQUIRED"] == "false"
    output = tmp_path / "outputs"
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=ROOT,
        env={
            **os.environ,
            **resolved,
            "GATE_PR_JSON": "",
            "GITHUB_EVENT_PATH": "",
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
            "GATE_ARTIFACTS_ROOT": str(tmp_path / "artifacts"),
            "PYTHON_RESULT": "skipped",
            "DOCS_GUARD_RESULT": docs_guard,
        },
        check=True,
    )
    receipt = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert receipt["state"] == expected
