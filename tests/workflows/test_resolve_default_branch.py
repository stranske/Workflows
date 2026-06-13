import re
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION_DIR = REPO_ROOT / ".github" / "actions" / "resolve-default-branch"
TEMPLATE_ACTION_DIR = (
    REPO_ROOT / "templates" / "consumer-repo" / ".github" / "actions" / "resolve-default-branch"
)


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
    assert "resolve-default-branch.js" in action["runs"]["steps"][0]["with"]["script"]

    assert (ACTION_DIR / "resolve-default-branch.js").read_text(encoding="utf-8") == (
        TEMPLATE_ACTION_DIR / "resolve-default-branch.js"
    ).read_text(encoding="utf-8")


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
    assert action_uses == 10
