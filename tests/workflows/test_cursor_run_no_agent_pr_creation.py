"""Keep Cursor on the existing PR and retain work when that PR closes mid-run."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/reusable-cursor-run.yml"


def test_cursor_cannot_create_prs_and_every_push_requires_an_open_target():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["cursor"]["steps"]
    run_index = next(i for i, step in enumerate(steps) if step.get("id") == "run_cursor")
    for token in ("GH_TOKEN", "GITHUB_TOKEN", "WORKFLOWS_TOKEN"):
        assert steps[run_index]["env"].get(token) == "", f"Run Cursor must clear {token}"

    gate_index = next(i for i, step in enumerate(steps) if step.get("id") == "target_pr")
    gate = steps[gate_index]
    assert run_index < gate_index
    assert "always()" in gate["if"]
    assert gate["env"]["PR_NUMBER"] == "${{ inputs.pr_number }}"
    assert "github.rest.pulls.get" in gate["with"]["script"]
    assert "pull.state === 'open'" in gate["with"]["script"]
    pushes = [i for i, step in enumerate(steps) if "git push " in step.get("run", "")]
    assert pushes, "Expected the existing workflow push paths"
    for push_index in pushes:
        assert gate_index < push_index
        assert "steps.target_pr.outputs.push_allowed == 'true'" in steps[push_index].get("if", "")


def test_source_issue_comment_permissions_and_prompt_mirror():
    callers = [
        WORKFLOW,
        ROOT / "templates/consumer-repo/.github/workflows/agents-81-gate-followups.yml",
    ]
    for path in callers:
        assert yaml.safe_load(path.read_text())["permissions"]["issues"] == "write", path
    for name, job in (
        ("agents-keepalive-loop.yml", "run-cursor"),
        ("agents-autofix-loop.yml", "autofix-cursor"),
    ):
        caller = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
        assert caller["permissions"].get("issues") != "write", name
        permissions = caller["jobs"][job]["permissions"]
        assert permissions["issues"] == "write", name
        # Explicit job permissions must preserve everything required by the callee.
        for scope, access in yaml.safe_load(WORKFLOW.read_text())["permissions"].items():
            assert permissions[scope] == access, (name, scope)
    prompt = Path(".github/codex/prompts/keepalive_next_task.md")
    instruction = (
        b"Do not create branches or pull requests; commit only to the checked-out PR branch."
    )
    for base in (ROOT, ROOT / "templates/consumer-repo"):
        assert instruction in (base / prompt).read_bytes()
    # Reusable workflows are consumed directly from Workflows, not copied.
    assert not (ROOT / "templates/consumer-repo/.github/workflows" / WORKFLOW.name).exists()


@pytest.mark.parametrize(
    "scenario",
    ["open", "merged", "closed", "duplicate", "no-commits", "no-issue", "no-pr", "api-error"],
)
def test_target_pr_guard_executes_with_real_unpushed_commits(tmp_path, scenario):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "Cursor fixture")
    git("config", "user.email", "cursor@example.invalid")
    git("config", "commit.gpgsign", "false")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "PR checkout", "--allow-empty")
    start = git("rev-parse", "HEAD")
    shas = []
    if scenario != "no-commits":
        for message in ("leftover one", "leftover two"):
            git("-c", "core.hooksPath=/dev/null", "commit", "-qm", message, "--allow-empty")
            shas.append(git("rev-parse", "HEAD"))

    # Execute the actual workflow JavaScript, including the real source resolver.
    helper = tmp_path / ".workflows-lib/.github/scripts/source_context.js"
    helper.parent.mkdir(parents=True)
    helper.symlink_to(ROOT / ".github/scripts/source_context.js")
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["cursor"]["steps"]
    script = next(step for step in steps if step.get("id") == "target_pr")["with"]["script"]
    harness = r"""
const fs = require('fs');
const { execFileSync } = require('child_process');
const { script, scenario } = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = { outputs: {}, comments: [], reads: [], notices: [], warnings: [], summary: '' };
const core = {
  setOutput: (key, value) => { result.outputs[key] = value; },
  info: () => {},
  notice: value => result.notices.push(value),
  warning: value => result.warnings.push(value),
  summary: {
    addRaw: value => { result.summary += value; return core.summary; },
    write: async () => {},
  },
};
const github = {
  rest: {
    pulls: { get: async args => {
      result.reads.push(args);
      if (scenario === 'api-error') throw new Error('PR lookup unavailable');
      return { data: {
        state: scenario === 'open' ? 'open' : 'closed',
        merged: scenario === 'merged',
        body: scenario === 'no-issue' ? '' : 'Closes #4562',
      } };
    } },
    issues: {
      listComments: () => {},
      createComment: async args => { result.comments.push(args); },
    },
  },
  paginate: async () => scenario === 'duplicate'
    ? [{ body: '<!-- cursor-target-closed:42:123 -->' }] : [],
};
const exec = { getExecOutput: async (file, args) => ({
  stdout: execFileSync(file, args, { encoding: 'utf8' }),
}) };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
(async () => {
  try {
    await new AsyncFunction('require', 'github', 'context', 'core', 'exec', script)(
      require, github, { repo: { owner: 'stranske', repo: 'Workflows' }, runId: 123 }, core, exec,
    );
  } catch (error) { result.error = error.message; }
  process.stdout.write(JSON.stringify(result));
})();
"""
    completed = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": script, "scenario": scenario}),
        env={
            **os.environ,
            "PR_NUMBER": "" if scenario == "no-pr" else "42",
            "START_SHA": start,
            "GITHUB_SERVER_URL": "https://github.com",
        },
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    result = json.loads(completed.stdout)
    assert result["outputs"]["push_allowed"] == ("true" if scenario == "open" else "false")
    assert result["reads"] == (
        []
        if scenario == "no-pr"
        else [{"owner": "stranske", "repo": "Workflows", "pull_number": 42}]
    )
    if scenario == "api-error":
        assert result["error"] == "PR lookup unavailable"
        assert result["comments"] == []
        return
    assert "error" not in result
    if scenario in {"open", "no-pr"}:
        assert result["comments"] == []
        assert result["summary"] == ""
        return
    assert result["outputs"]["outcome"] == "skipped: target PR merged/closed mid-run"
    assert "https://github.com/stranske/Workflows/actions/runs/123" in result["summary"]
    for sha in shas:
        assert sha in result["summary"]
    assert start not in result["summary"]
    if scenario == "no-commits":
        assert "- None." in result["summary"]
    if scenario in {"duplicate", "no-issue"}:
        assert result["comments"] == []
        if scenario == "no-issue":
            assert result["warnings"]
    else:
        assert len(result["comments"]) == 1
        assert result["comments"][0] == {
            "owner": "stranske",
            "repo": "Workflows",
            "issue_number": 4562,
            "body": result["summary"],
        }
