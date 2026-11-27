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
    assert resolve_step["env"]["REQUIRE_RETRY_HELPER"] == "${{ inputs.require_retry_helper }}"
    assert "requireRetryHelper: process.env.REQUIRE_RETRY_HELPER" in script
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
def test_integration_formatters_require_token_aware_retry(tmp_path) -> None:
    definition = yaml.safe_load(
        (REPO_ROOT / ".github/workflows/maint-71-auto-fix-integration.yml").read_text()
    )
    job = next(iter(definition["jobs"].values()))
    lookup = next(step for step in job["steps"] if step.get("id") == "integration_ref")
    assert lookup["uses"] == "./.github/actions/resolve-default-branch"
    assert lookup["with"]["repo"] == "Workflows-Integration-Tests"
    assert lookup["with"]["require_retry_helper"] == "true"

    # Simulate an incomplete checkout. Ordinary partial-checkout callers can still resolve.
    script = r"""
const assert = require('node:assert/strict');
const { resolveDefaultBranch } = require(process.argv[1]);
(async () => {
  for (const strict of [true, false]) {
    let reads = 0;
    const failures = [];
    const github = { rest: { repos: { get: async () => {
      reads++;
      return { data: { default_branch: 'release' } };
    } } } };
    const core = { setOutput() {}, setFailed(message) { failures.push(message); } };
    const ref = await resolveDefaultBranch({ github, core, env: {}, requireRetryHelper: strict });
    assert.equal(reads, strict ? 0 : 1);
    assert.equal(failures.length, strict ? 1 : 0);
    assert.equal(ref, strict ? '' : 'release');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(
        ["node", "-e", script, str(ACTION_DIR / "resolve-default-branch.js")],
        cwd=tmp_path,
        check=True,
    )


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


@pytest.mark.parametrize(
    ("ref", "expected_ref", "narrow"),
    [
        ("", "main", True),
        ("main", "main", True),
        ("refs/heads/main", "refs/heads/main", True),
        ("release/test", "release/test", False),
        ("refs/heads/release/test", "refs/heads/release/test", False),
        ("refs/tags/main", "refs/tags/main", False),
        ("v1.52.16", "v1.52.16", False),
        ("refs/tags/v1.52.16", "refs/tags/v1.52.16", False),
        ("a" * 40, "a" * 40, False),
    ],
)
def test_pr_meta_bootstraps_resolver_from_workflows_checkout(
    tmp_path: Path, ref: str, expected_ref: str, narrow: bool
) -> None:
    """Bootstrap from Workflows and preserve all dependencies on alternate refs."""
    workflow = REPO_ROOT / ".github" / "workflows" / "reusable-20-pr-meta.yml"
    steps = yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]["keepalive_dispatch"][
        "steps"
    ]
    determine_ref = next(step for step in steps if step.get("id") == "workflows_workflow_ref")
    assert determine_ref["env"]["WORKFLOW_REF"] == "${{ github.workflow_ref }}"
    caller = "stranske/trip-planner/.github/workflows/agents-80-pr-event-hub.yml"
    output = tmp_path / "workflow-output"
    subprocess.run(
        ["bash", "-c", determine_ref["run"]],
        env={"WORKFLOW_REF": f"{caller}@{ref}" if ref else caller, "GITHUB_OUTPUT": str(output)},
        check=True,
    )
    ref_line, opener, *paths, delimiter = output.read_text().splitlines()
    assert ref_line == f"ref={expected_ref}"
    assert opener == "sparse_checkout<<RESOLVER_PATHS"
    assert delimiter == "RESOLVER_PATHS"
    assert paths[0] == ".github/actions/resolve-default-branch"
    if narrow:
        assert paths[1:] == [
            ".github/scripts/error_classifier.js",
            ".github/scripts/github-api-with-retry.js",
            ".github/scripts/package.json",
            ".github/scripts/token_load_balancer.js",
        ]
    else:
        assert paths[1:] == [".github/scripts"]

    bootstrap = next(step for step in steps if step["name"] == "Checkout resolver action")
    assert bootstrap["uses"] == "actions/checkout@v7"
    assert bootstrap["with"]["repository"] == "stranske/Workflows"
    assert bootstrap["with"]["path"] == "workflows-resolver"
    assert bootstrap["with"]["ref"] == "${{ steps.workflows_workflow_ref.outputs.ref }}"
    assert bootstrap["with"]["sparse-checkout"] == (
        "${{ steps.workflows_workflow_ref.outputs.sparse_checkout }}"
    )
    determine_default = next(step for step in steps if step.get("id") == "workflows_ref")
    assert (
        determine_default["uses"] == "./workflows-resolver/.github/actions/resolve-default-branch"
    )
    library = next(step for step in steps if step["name"] == "Checkout Workflows scripts")
    assert library["with"]["ref"] == "${{ steps.workflows_ref.outputs.ref }}"
    assert library["with"]["path"] == "workflows-lib"
    assert ".github/scripts" in library["with"]["sparse-checkout"].splitlines()
