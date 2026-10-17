"""The source issue exception runs untrusted gates away from closure credentials."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_incomplete_input_closure_is_wired_through_isolated_merge_gates():
    reusable = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    verifier = reusable["jobs"]["verifier"]
    assert set(reusable["jobs"]) == {"verifier"}  # Old read-only callers remain compatible.
    assert verifier["outputs"]["verdict"] == "${{ steps.unified_verdict.outputs.verdict }}"
    assert (
        reusable[True]["workflow_call"]["outputs"]["verdict"]["value"]
        == "${{ jobs.verifier.outputs.verdict }}"
    )
    assert "source_hash" in str(verifier)
    for relative in [
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
    ]:
        jobs = yaml.safe_load((ROOT / relative).read_text())["jobs"]
        gates, closer = jobs["acceptance-gates"], jobs["close-sources"]
        assert gates["permissions"] == {"contents": "read"}
        assert "UNVERIFIABLE_INPUT" in gates["if"]
        assert "secrets." not in str(gates)
        assert "setup-api-client" not in str(gates)
        checkout = next(
            step for step in gates["steps"] if step["name"] == "Checkout immutable merge commit"
        )
        assert checkout["with"]["ref"] == "${{ needs.verifier.outputs.target_sha }}"
        assert checkout["with"]["persist-credentials"] is False
        assert "'--prepare'" in str(gates)
        assert closer["needs"] == ["verifier", "acceptance-gates"]
        assert "needs.acceptance-gates.result == 'success'" in closer["if"]
        assert closer["permissions"]["issues"] == "write"
        assert jobs["verifier"]["permissions"]["issues"] == "read"
        assert "closeVerifiedSources" in str(closer)
        assert "includeHeadSha: true" in str(closer)
        ci_step = next(
            step
            for step in closer["steps"]
            if step["name"] == "Close eligible source issues with rule receipt"
        )
        assert ci_step["env"]["CI_WORKFLOWS"] == jobs["verifier"]["with"]["ci_workflows"]


def test_intake_replay_preserves_trusted_verifier_closures():
    """Execute the marker guard used before the intake workflow's reopen write."""
    import subprocess

    workflow = yaml.safe_load((ROOT / ".github/workflows/agents-63-issue-intake.yml").read_text())
    scripts = [
        step.get("with", {}).get("script", "")
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    ]
    script = next(s for s in scripts if "function isVerificationClosure" in s)
    start = script.index("if (needsStateChange) {\n")
    end = script.index("const existingTitle", start)
    guard = script[start:end]
    node = r"""
    const assert = require('node:assert/strict');
    const guard = GUARD;
    async function replay(comment) {
      let reopened = false;
      let skippedCount = 0;
      const needsStateChange = true, owner = 'owner', repo = 'repo', issueNumber = 123;
      const core = { info() {} };
      const github = { rest: {issues: {listComments() {}}}, paginate: async () => [comment] };
      const withRetry = fn => fn();
      for (const seed of [123]) {
        GUARD_CODE
        reopened = true;
      }
      return reopened;
    }
    (async () => {
      for (const [rule, verdict] of [
        ['verifier-pass', 'PASS'],
        ['unverifiable-input-merged-head-gates-and-ci', 'UNVERIFIABLE_INPUT'],
      ]) {
        const comment = { user: {type: 'Bot', login: 'github-actions[bot]'},
          body: `Verification closure rule: **${rule}**. PR #5, merge commit \`${'a'.repeat(40)}\`, verdict **${verdict}**.` };
        assert.equal(await replay(comment), false);
        assert.equal(await replay({...comment, user: {type: 'User', login: 'github-actions[bot]'}}), true);
        assert.equal(await replay({...comment, body: 'untrusted mention of ' + rule}), true);
      }
    })().catch(error => { console.error(error); process.exit(1); });
    """.replace("const guard = GUARD;", "").replace("GUARD_CODE", guard)
    subprocess.run(["node", "-e", node], cwd=ROOT, check=True, capture_output=True, text=True)


def test_auto_pilot_closed_issue_verification_does_not_reopen_sources():
    # Auto-pilot requests verifier labels; the state-changing reopen path is intake.
    for relative in [
        ".github/workflows/agents-auto-pilot.yml",
        "templates/consumer-repo/.github/workflows/agents-auto-pilot.yml",
    ]:
        workflow = yaml.safe_load((ROOT / relative).read_text())
        steps = [step for job in workflow["jobs"].values() for step in job.get("steps", [])]
        script = next(step["with"]["script"] for step in steps if step.get("id") == "verify_step")
        assert "issues.update" not in script
        assert "issues.addLabels" in script


def test_checkbox_prompt_exceeding_argument_limit_reaches_cli_over_stdin(tmp_path):
    import os
    import subprocess

    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    steps = workflow["jobs"]["verifier"]["steps"]
    run = next(step["run"] for step in steps if '"$CODEX_CLI" exec' in step.get("run", ""))
    start = run.index('"$CODEX_CLI" exec')
    command = run[start : run.index("codex_exit_code=$?", start)]
    binary = tmp_path / "fake-codex"
    binary.write_text('#!/bin/sh\ncat > "$RECEIVED_PROMPT"\n')
    binary.chmod(0o755)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("complete changed-file input\n" * 100000)
    received = tmp_path / "received.md"
    subprocess.run(
        ["bash", "-c", command],
        cwd=tmp_path,
        check=True,
        env={
            **os.environ,
            "CODEX_CLI": str(binary),
            "PROMPT_FILE": str(prompt),
            "RECEIVED_PROMPT": str(received),
            "codex_model": "test",
        },
    )
    assert received.read_bytes() == prompt.read_bytes()


def test_closure_ci_lists_only_post_merge_workflows():
    for relative in [
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
    ]:
        import json

        workflow = yaml.safe_load((ROOT / relative).read_text())
        ci_workflows = json.loads(workflow["jobs"]["verifier"]["with"]["ci_workflows"])
        assert ci_workflows
        assert "pr-00-gate.yml" not in ci_workflows


def test_ci_wait_does_not_substitute_completed_pr_head_for_merge_commit():
    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    wait = next(s for s in workflow["jobs"]["verifier"]["steps"] if s.get("id") == "wait_ci")
    script = wait["with"]["script"]
    assert "[pr.merge_commit_sha]" in script
    assert "pr.head?.sha" not in script


def test_closure_plan_lookup_failure_does_not_abort_other_issues(tmp_path):
    import json
    import subprocess

    workflow = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    step = next(
        s
        for s in workflow["jobs"]["verifier"]["steps"]
        if s.get("name") == "Prepare source closure plans"
    )
    script = step["with"]["script"]
    # Execute the actual workflow script with failed, changed, and valid issue reads.
    script = script.replace(
        "require('./.workflows-lib/.github/scripts/verifier_closure.js')",
        f"require({json.dumps(str(ROOT / '.github/scripts/verifier_closure.js'))})",
    )
    script = script.replace(
        "const { withRetry } = require('./.workflows-lib/.github/scripts/github-api-with-retry.js');",
        "const withRetry = fn => fn();",
    )
    harness = r"""
    const assert = require('node:assert/strict');
    const {sourceHash} = require(CLOSURE);
    process.env.ISSUE_NUMBERS = '[1,2,3]';
    process.env.SOURCE_ISSUE_HASHES = JSON.stringify({2: sourceHash('old'),3: sourceHash('valid')});
    const context = {repo:{owner:'owner',repo:'repo'}};
    const warnings=[];
    const core = {warning: message => warnings.push(message)};
    const github = {rest:{issues:{get: async ({issue_number}) => {
      if(issue_number === 1) throw new Error('unavailable');
      return {data:{body: issue_number === 2 ? 'changed' : 'valid'}};
    }}}};
    (async () => {
      SCRIPT
      assert.equal(warnings.length, 2);
      assert.deepEqual(JSON.parse(require('fs').readFileSync('closure-plans/plans.json')).map(p=>p.issue_number), [3]);
    })().catch(error=>{ console.error(error); process.exit(1); });
    """.replace("CLOSURE", json.dumps(str(ROOT / ".github/scripts/verifier_closure.js"))).replace(
        "SCRIPT", script
    )
    subprocess.run(
        ["node", "-e", harness], cwd=tmp_path, check=True, capture_output=True, text=True
    )
