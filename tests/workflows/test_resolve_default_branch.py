import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "resolve-default-branch"
TEMPLATE_ACTION_DIR = (
    REPO_ROOT / "templates" / "consumer-repo" / ".github" / "actions" / "resolve-default-branch"
)
skip_if_no_node = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js required")


def test_resolve_default_branch_action_contract_and_template_copy() -> None:
    action = yaml.safe_load((ACTION_DIR / "action.yml").read_text(encoding="utf-8"))
    template_action = yaml.safe_load(
        (TEMPLATE_ACTION_DIR / "action.yml").read_text(encoding="utf-8")
    )

    assert action == template_action
    assert action["outputs"]["ref"]["value"] == "${{ steps.resolve.outputs.ref }}"
    assert action["inputs"]["owner"]["default"] == "stranske"
    assert action["inputs"]["repo"]["default"] == "Workflows"
    assert action["runs"]["steps"][0]["uses"] == "actions/github-script@v9"
    resolve_step = action["runs"]["steps"][0]
    assert resolve_step["env"]["RESOLVE_DEFAULT_BRANCH_ACTION_PATH"] == "${{ github.action_path }}"
    script = resolve_step["with"]["script"]
    assert "resolve-default-branch.js" in script
    assert "RESOLVE_DEFAULT_BRANCH_ACTION_PATH" in script
    assert "GITHUB_ACTION_PATH" not in script

    assert (ACTION_DIR / "resolve-default-branch.js").read_text(encoding="utf-8") == (
        TEMPLATE_ACTION_DIR / "resolve-default-branch.js"
    ).read_text(encoding="utf-8")


def test_retry_helper_prefers_explicit_resolver_action_path() -> None:
    script = (ACTION_DIR / "resolve-default-branch.js").read_text(encoding="utf-8")
    assert "RESOLVE_DEFAULT_BRANCH_ACTION_PATH" in script
    assert script.index("resolverActionPath") < script.index("actionPath ?")


@skip_if_no_node
def test_resolve_default_branch_logic_with_stubbed_client() -> None:
    script = r"""
const assert = require('assert');
const { resolveDefaultBranch } = require('./.github/actions/resolve-default-branch/resolve-default-branch.js');

(async () => {
  const outputs = {};
  const failures = [];
  const warnings = [];
  const calls = [];
  const github = {
    rest: {
      repos: {
        get: async (args) => {
          calls.push(args);
          return { data: { default_branch: 'main' } };
        },
      },
    },
  };
  const core = {
    setOutput: (name, value) => {
      outputs[name] = value;
    },
    setFailed: (message) => failures.push(message),
    warning: (message) => warnings.push(message),
  };

  const ref = await resolveDefaultBranch({
    github,
    core,
    owner: 'stranske',
    repo: 'Workflows',
    env: {},
    cwd: process.cwd(),
  });

  assert.strictEqual(ref, 'main');
  assert.strictEqual(outputs.ref, 'main');
  assert.deepStrictEqual(calls, [{ owner: 'stranske', repo: 'Workflows' }]);
  assert.deepStrictEqual(failures, []);
  assert.deepStrictEqual(warnings, []);
})();
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


@skip_if_no_node
def test_resolve_default_branch_fallback_preserves_lenient_callers() -> None:
    script = r"""
const assert = require('assert');
const { resolveDefaultBranch } = require('./.github/actions/resolve-default-branch/resolve-default-branch.js');

(async () => {
  const outputs = {};
  const warnings = [];
  const github = {
    rest: {
      repos: {
        get: async () => {
          throw new Error('network unavailable');
        },
      },
    },
  };
  const core = {
    setOutput: (name, value) => {
      outputs[name] = value;
    },
    setFailed: (message) => {
      throw new Error(`unexpected failure: ${message}`);
    },
    warning: (message) => warnings.push(message),
  };

  const ref = await resolveDefaultBranch({
    github,
    core,
    fallbackRef: 'main',
    failOnError: false,
    env: {},
    cwd: process.cwd(),
  });

  assert.strictEqual(ref, 'main');
  assert.strictEqual(outputs.ref, 'main');
  assert.strictEqual(warnings.length, 1);
  assert.match(warnings[0], /using main/);
})();
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_resolve_default_branch_inline_workflow_copies_removed() -> None:
    workflow_dirs = [
        REPO_ROOT / ".github" / "workflows",
        REPO_ROOT / "templates" / "consumer-repo" / ".github" / "workflows",
    ]
    texts = {
        path: path.read_text(encoding="utf-8")
        for workflow_dir in workflow_dirs
        for path in workflow_dir.glob("*.yml")
    }

    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path, text in texts.items()
        if "Resolve Workflows default branch" in text
    ]
    assert offenders == []

    uses_pattern = re.compile(r"^\s*uses:\s+.*resolve-default-branch(?:@.*)?$", re.MULTILINE)
    action_uses = sum(len(uses_pattern.findall(text)) for text in texts.values())
    assert action_uses >= 10


def test_pr_meta_bootstraps_resolver_from_workflows_checkout() -> None:
    """PR meta cannot require unsynced consumers to already have the new action."""
    assert_workflow_bootstraps_resolver_from_workflows_checkout("reusable-20-pr-meta.yml")


def test_keepalive_bootstraps_resolver_from_workflows_checkout() -> None:
    """Keepalive cannot require unsynced consumers to already have the new action."""
    assert_workflow_bootstraps_resolver_from_workflows_checkout("reusable-16-agents.yml")


def assert_workflow_bootstraps_resolver_from_workflows_checkout(workflow_name: str) -> None:
    workflow = REPO_ROOT / ".github" / "workflows" / workflow_name
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    steps = next(
        job["steps"]
        for job in data["jobs"].values()
        if any(step.get("name") == "Resolve Workflows ref" for step in job.get("steps", []))
    )

    resolver_checkout = next(
        step for step in steps if step.get("name") == "Checkout resolver action"
    )
    assert resolver_checkout["uses"] == "actions/checkout@v6"
    assert resolver_checkout["with"]["path"] == "workflows-resolver"
    assert ".github/actions/resolve-default-branch" in resolver_checkout["with"]["sparse-checkout"]

    resolve_step = next(step for step in steps if step.get("name") == "Resolve Workflows ref")
    assert resolve_step["uses"] == "./workflows-resolver/.github/actions/resolve-default-branch"
    assert "./consumer/.github/actions/resolve-default-branch" not in workflow.read_text(
        encoding="utf-8"
    )
