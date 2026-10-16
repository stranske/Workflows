"""Issue intake must route the LABELLED agent, not codex (Workflows#3930).

Runs the real `Normalize inputs` step of agents-63-issue-intake.yml under bash with an
`issues` event payload, so a hard-coded default would fail here.
"""

import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
INTAKE = ROOT / ".github/workflows/agents-63-issue-intake.yml"


def _normalize_script() -> str:
    jobs = yaml.safe_load(INTAKE.read_text())["jobs"]
    steps = jobs["normalize_inputs"]["steps"]
    return next(s["run"] for s in steps if s.get("id") == "normalize")


def _run(tmp_path: Path, labels: list[str], env_extra: dict | None = None) -> dict:
    event = {"issue": {"number": 7, "labels": [{"name": n} for n in labels]}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    out = tmp_path / "out.txt"
    out.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "GITHUB_EVENT_NAME": "issues",
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_OUTPUT": str(out),
    }
    env.update(env_extra or {})
    subprocess.run(["bash", "-c", _normalize_script()], env=env, check=True, capture_output=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)


def test_intake_routes_the_labelled_agent_not_codex(tmp_path):
    for agent in ("cursor", "muse", "codex"):
        key = _run(tmp_path, [f"agent:{agent}"])["bridge_agent"]
        assert key == agent
        command = (
            "const registry = require(process.argv[1]);"
            "console.log(registry.getRunnerWorkflow(process.argv[2]));"
        )
        runner = subprocess.run(
            ["node", "-e", command, str(ROOT / ".github/scripts/agent_registry.js"), key],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert runner == f".github/workflows/reusable-{agent}-run.yml"
    assert _run(tmp_path, ["bug"])["bridge_agent"] == "codex"  # no agent label: unchanged default


def test_post_agent_comment_is_the_neutral_name_and_post_codex_comment_still_works(tmp_path):
    neutral = _run(tmp_path, ["agent:cursor"], {"INPUT_POST_AGENT_COMMENT": "false"})
    assert neutral["post_agent_comment"] == "false"
    legacy = _run(tmp_path, ["agent:cursor"], {"INPUT_POST_CODEX_COMMENT": "false"})
    assert legacy["post_agent_comment"] == "false"
    assert legacy["post_codex_comment"] == "false"
    default = _run(tmp_path, ["agent:cursor"])
    assert default["post_agent_comment"] == "true"


def test_bridge_receives_the_neutral_output():
    text = INTAKE.read_text()
    assert "post_agent_comment: ${{ needs.normalize_inputs.outputs.post_agent_comment }}" in text


def test_dispatch_defaults_preserve_legacy_comment_behavior(tmp_path):
    workflow = yaml.safe_load(INTAKE.read_text())
    inputs = (workflow.get("on") or workflow[True])["workflow_dispatch"]["inputs"]
    default = inputs["post_agent_comment"].get(
        "default", False if inputs["post_agent_comment"]["type"] == "boolean" else ""
    )
    neutral = str(default).lower() if isinstance(default, bool) else default
    result = _run(
        tmp_path,
        ["agent:codex"],
        {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "INPUT_POST_AGENT_COMMENT": neutral,
            "INPUT_POST_CODEX_COMMENT": "true",
        },
    )
    assert result["post_agent_comment"] == "true"
    result = _run(
        tmp_path,
        ["agent:codex"],
        {
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "INPUT_POST_AGENT_COMMENT": "false",
            "INPUT_POST_CODEX_COMMENT": "true",
        },
    )
    assert result["post_agent_comment"] == "false"


def _bridge_steps():
    bridge = ROOT / ".github/workflows/reusable-agents-issue-bridge.yml"
    workflow = yaml.safe_load(bridge.read_text())
    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]


def _custom_invite_registry(tmp_path):
    registry = tmp_path / "registry.yml"
    text = (ROOT / ".github/agents/registry.yml").read_text()
    start = text.index("\n  cursor:")
    end = text.index("\n  muse:", start)
    cursor = text[start:end].replace(
        "assign_user: stranske-automation-bot", "assign_user: cursor-intake-bot"
    )
    cursor = cursor.replace("command_phrase: ''", "command_phrase: '@cursor implement this issue'")
    registry.write_text(text[:start] + cursor + text[end:])
    return registry


def _execute_bridge_script(script, registry, *, agent="cursor", suffix=""):
    # Exercise the real registry and bridge JS; only GitHub side effects/retry
    # transport are fake. This is local wiring proof, never a hosted canary.
    program = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const registry = require(input.module);
const captured = [];
const github = {rest:{issues:{createComment: async value => captured.push(value),
  get: async () => ({data:{title:'Canary',body:'## Tasks\n- [ ] Native run'}})},
  pulls:{list:async () => ({data:[]})}}};
function localRequire(name) {
  if (name.endsWith('agent_registry.js')) return {
    ...registry,
    getIssueIntakeConfig: key => registry.getIssueIntakeConfig(key, {registryPath:input.registry}),
  };
  if (name.endsWith('github-api-with-retry.js')) return {
    withRetry: fn => fn(),
    createTokenAwareRetry: async () => ({github, withRetry: fn => fn()}),
  };
  if (name.endsWith('issue_context_utils.js')) return {
    buildIssueContext: () => ({statusSummaryBlock:'',formattedBody:'## Tasks'}),
  };
  if (name.endsWith('keepalive_instruction_template.js')) return {
    getKeepaliveInstructionWithMention: () => 'unchanged instruction',
  };
  return require(name);
}
process.env.AGENT = input.agent;
process.env.BRANCH = 'cursor/issue-7';
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require','github','core','context','agentKey',input.script + input.suffix)(
  localRequire, github, {setFailed: message => {throw Error(message)}, warning:()=>{}, info:()=>{}, error:()=>{}},
  {repo:{owner:'example',repo:'canary'}}, input.agent,
).then(result => console.log(JSON.stringify({captured,result}))).catch(error => {
  console.error(error); process.exit(1);
});
"""
    script = script.replace("${{ steps.pr.outputs.number }}", "7")
    script = script.replace("${{ steps.ctx.outputs.issue }}", "7")
    script = script.replace("${{ steps.refs.outputs.base }}", "main")
    result = subprocess.run(
        ["node", "-e", program],
        cwd=ROOT,
        input=json.dumps(
            {
                "script": script,
                "registry": str(registry),
                "module": str(ROOT / ".github/scripts/agent_registry.js"),
                "agent": agent,
                "suffix": suffix,
            }
        ),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_bridge_posts_registry_command_in_all_invitation_paths(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    names = [
        "Post agent command as service user",
        "Post agent command (fallback as github-actions)",
        "Prompt human to post agent command",
    ]
    steps = _bridge_steps()
    for name in names:
        script = next(step["with"]["script"] for step in steps if step.get("name") == name)
        result = _execute_bridge_script(script, registry)
        assert len(result["captured"]) == 1
        body = result["captured"][0]["body"]
        assert "@cursor implement this issue" in body
        assert "@cursor start" not in body


def test_bridge_assignment_honors_registry_and_preserves_legacy_assignees(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    script = next(
        step["with"]["script"]
        for step in _bridge_steps()
        if "let assignees =" in step.get("with", {}).get("script", "")
    )
    start = script.index("let assignees =")
    end = script.index("try {\n  await withRetry", start)
    assignment = script[start:end]
    for agent, expected in [
        ("cursor", ["cursor-intake-bot", "stranske-automation-bot"]),
        ("codex", ["chatgpt-codex-connector", "stranske-automation-bot"]),
        ("claude", ["stranske-automation-bot"]),
    ]:
        result = _execute_bridge_script(
            assignment, registry, agent=agent, suffix="\nreturn assignees;"
        )
        assert result["result"] == expected


def test_invite_mode_names_registry_assignee_and_command_without_creating_pr(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    script = next(
        step["with"]["script"]
        for step in _bridge_steps()
        if step.get("name") == "Invite human to open PR (invite mode)"
    )
    result = _execute_bridge_script(script, registry)
    assert len(result["captured"]) == 1
    body = result["captured"][0]["body"]
    assert "cursor-intake-bot" in body
    assert "@cursor implement this issue" in body
    assert "PR creation is disabled by design" in body


def test_registry_keeps_legacy_mention_default_when_no_command_is_configured():
    program = """const r = require(process.argv[1]);
console.log(r.getIssueIntakeConfig('codex', {defaultCommand:'@legacy-bot start'}).command_phrase);
console.log(r.getIssueIntakeConfig('claude').command_phrase);"""
    result = subprocess.run(
        ["node", "-e", program, str(ROOT / ".github/scripts/agent_registry.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == ["@legacy-bot start", "@claude start"]
