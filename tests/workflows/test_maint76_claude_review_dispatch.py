from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
from typing import Any

import pytest
import yaml

WORKFLOW = pathlib.Path("templates/consumer-repo/.github/workflows/maint-76-claude-code-review.yml")

RUNNER_JS = """\
const fs = require("fs");
const path = require("path");

const [stepPath, inputsJson] = process.argv.slice(2);
const body = fs.readFileSync(stepPath, "utf8");
const inputs = JSON.parse(inputsJson);
const fn = new (Object.getPrototypeOf(async function () {}).constructor)(
  "context",
  "github",
  "core",
  "require",
  body,
);

(async () => {
  const outputs = {};
  const warnings = [];
  let requestedPullNumber = null;
  const context = {
    eventName: "workflow_dispatch",
    payload: { inputs },
    repo: { owner: "stranske", repo: "Workflows" },
  };
  const github = {
    rest: {
      pulls: {
        get: async ({ pull_number }) => {
          requestedPullNumber = pull_number;
          return {
            data: {
              number: pull_number,
              state: "open",
              draft: false,
            },
          };
        },
      },
    },
  };
  const core = {
    getInput: () => "",
    setOutput: (name, value) => {
      outputs[name] = value;
    },
    warning: (msg) => {
      warnings.push(String(msg));
    },
  };

  await fn(context, github, core, require);
  process.stdout.write(
    JSON.stringify({
      outputs,
      requestedPullNumber,
      warnings,
    }),
  );
})();
"""


def _extract_resolve_script() -> str:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["resolve-target"]["steps"]
    for step in steps:
        if step.get("id") == "resolve":
            return str(step["with"]["script"])
    raise AssertionError(f"{WORKFLOW} no longer defines a resolve step")


def _run_dispatch_resolve(tmp_path: pathlib.Path, inputs: dict[str, str]) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:  # pragma: no cover - depends on the host
        message = "node is required to execute maint-76 resolve github-script step"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)

    step_path = tmp_path / "step.js"
    step_path.write_text(_extract_resolve_script(), encoding="utf-8")
    runner_path = tmp_path / "runner.js"
    runner_path.write_text(RUNNER_JS, encoding="utf-8")

    completed = subprocess.run(
        [node, str(runner_path), str(step_path), json.dumps(inputs)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return dict(json.loads(completed.stdout))


def test_dispatch_pr_number_read_from_event_payload_not_action_input() -> None:
    # workflow_dispatch inputs live in context.payload.inputs; core.getInput reads
    # INPUT_* env vars that actions/github-script only sets from its own `with:`.
    source = WORKFLOW.read_text(encoding="utf-8")
    assert source.count("context.payload.inputs") == 1
    assert "(context.payload.inputs || {}).pr_number" in source
    assert source.count('core.getInput("pr_number")') == 0


def test_dispatch_resolves_pr_number_from_event_payload_inputs(tmp_path: pathlib.Path) -> None:
    resolved = _run_dispatch_resolve(tmp_path, {"pr_number": "42"})
    assert resolved["requestedPullNumber"] == 42
    assert resolved["outputs"] == {
        "should_run": "true",
        "pr_number": "42",
        "reason": "manual_dispatch",
    }

    rejected = _run_dispatch_resolve(tmp_path, {"other": "42"})
    assert rejected["requestedPullNumber"] is None
    assert rejected["outputs"] == {
        "should_run": "false",
        "pr_number": "",
        "reason": "invalid_pr_number",
    }
