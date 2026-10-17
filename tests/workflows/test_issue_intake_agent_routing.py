"""Issue intake must route the LABELLED agent, not codex (Workflows#3930).

Runs the real `Normalize inputs` step of agents-63-issue-intake.yml under bash with an
`issues` event payload, so a hard-coded default would fail here.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
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
    assert _run(tmp_path, ["bug"])["bridge_agent"] == ""  # preflight resolves the default
    assert _run(tmp_path, ["agent:auto"])["bridge_agent"] == "auto"


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


def _execute_bridge_script(
    script, registry, *, agent="cursor", suffix="", existing_pr=False, mention=""
):
    # Exercise the real registry and bridge JS; only GitHub side effects/retry
    # transport are fake. This is local wiring proof, never a hosted canary.
    program = r"""
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const registry = require(input.module);
const captured = [];
const github = {rest:{issues:{createComment: async value => captured.push(value),
  get: async () => ({data:{title:'Canary',body:'## Tasks\n- [ ] Native run'}})},
  pulls:{list:async () => ({data:input.existing_pr ? [{number:8,
    body:'<!-- meta:issue:7 --><!-- auto-status-summary:start --> already populated body',
    html_url:'https://example.invalid/pull/8'}] : []})}}};
function localRequire(name) {
  if (name.endsWith('agent_registry.js')) return {
    ...registry,
    getAgentConfig: key => registry.getAgentConfig(key, {registryPath:input.registry}),
  };
  if (name.endsWith('github-api-with-retry.js')) return {
    withRetry: fn => fn(),
    createTokenAwareRetry: async () => ({github, withRetry: fn => fn(), paginateWithRetry:async () => []}),
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
process.env.BRIDGE_AGENT_MENTION = input.mention;
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const outputs = {};
const core = {setFailed: message => {throw Error(message)}, warning:()=>{}, info:()=>{}, error:()=>{},
  setOutput: (key,value) => {outputs[key]=value}};
async function main() {
  await new AsyncFunction('require','core',input.prelude)(localRequire,core);
  process.env.INTAKE_COMMAND = outputs.command;
  process.env.INTAKE_ASSIGNEES = outputs.assignees;
  const result = await new AsyncFunction('require','github','core','context','agentKey',input.script + input.suffix)(
    localRequire, github, core, {repo:{owner:'example',repo:'canary'}}, input.agent);
  console.log(JSON.stringify({captured,result,outputs}));
}
main().catch(error => {console.error(error); process.exit(1)});
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
                "prelude": next(
                    step["with"]["script"]
                    for step in _bridge_steps()
                    if step.get("name") == "Resolve post-agent comment flag"
                ),
                "registry": str(registry),
                "module": str(ROOT / ".github/scripts/agent_registry.js"),
                "agent": agent,
                "suffix": suffix,
                "existing_pr": existing_pr,
                "mention": mention,
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
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


def test_registry_preserves_legacy_defaults_when_command_hint_is_empty(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    for agent, assignees in [
        ("codex", ["chatgpt-codex-connector", "stranske-automation-bot"]),
        ("claude", ["stranske-automation-bot"]),
    ]:
        result = _execute_bridge_script("", registry, agent=agent)
        assert result["outputs"]["command"] == ""
        assert json.loads(result["outputs"]["assignees"]) == assignees


def test_existing_pr_invite_still_names_the_resolved_instructions(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    script = next(
        step["with"]["script"]
        for step in _bridge_steps()
        if step.get("name") == "Invite human to open PR (invite mode)"
    )
    result = _execute_bridge_script(script, registry, existing_pr=True)
    note = next(x["body"] for x in result["captured"] if "already exists for branch" in x["body"])
    assert "cursor-intake-bot" in note
    assert "@cursor implement this issue" in note


def test_original_issue_link_preserves_legacy_mention_and_configured_command(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    script = next(
        step["with"]["script"]
        for step in _bridge_steps()
        if step.get("name") == "Link PR on original issue (fallback)"
    )
    for agent, expected in [
        ("codex", "@legacy-bot start"),
        ("cursor", "@cursor implement this issue"),
    ]:
        result = _execute_bridge_script(script, registry, agent=agent, mention="@legacy-bot")
        assert expected in result["captured"][0]["body"]


def test_shared_invitation_resolver_normalizes_mixed_case_agent_keys(tmp_path):
    registry = _custom_invite_registry(tmp_path)
    cursor = _execute_bridge_script("", registry, agent="CuRsOr")["outputs"]
    assert cursor["command"] == "@cursor implement this issue"
    assert json.loads(cursor["assignees"]) == ["cursor-intake-bot", "stranske-automation-bot"]
    codex = _execute_bridge_script("", registry, agent="CoDeX")["outputs"]
    assert codex["command"] == ""
    assert json.loads(codex["assignees"]) == ["chatgpt-codex-connector", "stranske-automation-bot"]


def test_qualified_cursor_preflight_is_enabled_without_enabling_muse():
    root = (ROOT / ".github/agents/registry.yml").read_bytes()
    template = (ROOT / "templates/consumer-repo/.github/agents/registry.yml").read_bytes()
    assert root == template
    agents = yaml.safe_load(root)["agents"]
    assert agents["cursor"]["preflight"]["enabled"] is True
    assert agents["muse"]["preflight"]["enabled"] is False
    program = "const r=require(process.argv[1]);console.log(JSON.stringify(r.getAgentPreflightConfigs()));"
    result = subprocess.run(
        ["node", "-e", program, str(ROOT / ".github/scripts/agent_registry.js")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    cursor = next(x for x in json.loads(result.stdout) if x["key"] == "cursor")
    assert cursor["assign_user"] == agents["cursor"]["preflight"]["assign_user"]


@pytest.mark.parametrize(
    ("payload_root", "workflow_path", "job", "step_name"),
    [
        (ROOT, INTAKE, "bridge_preflight", "Checkout retry helpers"),
        (
            ROOT / "templates/consumer-repo",
            ROOT / "templates/consumer-repo/.github/workflows/agents-issue-intake.yml",
            "check_labels",
            "Checkout delegation policy and registry",
        ),
    ],
    ids=["source", "consumer-alias"],
)
def test_preflight_sparse_checkout_loads_policy_and_receipt_dependencies(
    tmp_path, payload_root, workflow_path, job, step_name
):
    """The authored checkout must deliver the real policy's transitive payload."""
    steps = yaml.safe_load(workflow_path.read_text())["jobs"][job]["steps"]
    checkout = next(step for step in steps if step.get("name") == step_name)
    assert checkout["with"]["sparse-checkout-cone-mode"] is False
    for entry in checkout["with"]["sparse-checkout"].splitlines():
        entry = entry.strip()
        if not entry:
            continue
        source = payload_root / entry
        destination = tmp_path / entry
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    result = subprocess.run(
        [
            "node",
            "-e",
            """
const policy = require('./.github/scripts/agent_delegation_policy.js');
const receipt = require('./.github/scripts/rate_limit_receipt.js');
const config = require('./.github/scripts/rate_limit_receipt.json');
const completed = Date.parse('2026-10-17T00:00:00Z');
const record = { completed_at: new Date(completed).toISOString(),
                 completion: { reason: 'rate_limited' } };
const expiry = completed + config.RATE_LIMIT_RECEIPT_TTL_HOURS * 60 * 60 * 1000;
console.log(JSON.stringify({
  chooser: typeof policy.chooseAgentForIntake,
  ttl: receipt.RATE_LIMIT_RECEIPT_TTL_HOURS,
  beforeExpiry: receipt.rateLimitExpired(record, expiry - 1),
  atExpiry: receipt.rateLimitExpired(record, expiry),
}));
""",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    configured_ttl = json.loads(
        (payload_root / ".github/scripts/rate_limit_receipt.json").read_text()
    )["RATE_LIMIT_RECEIPT_TTL_HOURS"]
    assert configured_ttl > 0
    assert json.loads(result.stdout) == {
        "chooser": "function",
        "ttl": configured_ttl,
        "beforeExpiry": False,
        "atExpiry": True,
    }

    # Node can resolve the same-basename JSON when the JS helper is absent;
    # exercise the helper export as well as the policy import in both controls.
    for filename in ("rate_limit_receipt.js", "rate_limit_receipt.json"):
        dependency = tmp_path / ".github/scripts" / filename
        payload = dependency.read_bytes()
        dependency.unlink()
        try:
            missing = subprocess.run(result.args, cwd=tmp_path, capture_output=True, text=True)
            assert missing.returncode != 0, f"Missing {filename} went undetected"
            assert "Cannot find module" in missing.stderr
        finally:
            dependency.write_bytes(payload)
    restored = subprocess.run(result.args, cwd=tmp_path, capture_output=True, text=True)
    assert restored.returncode == 0, restored.stderr
    assert restored.stdout == result.stdout
