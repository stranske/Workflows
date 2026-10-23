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
        gate_script = next(s["run"] for s in gates["steps"] if "run" in s)
        assert "'--prepare'" in gate_script
        assert closer["needs"] == ["verifier", "acceptance-gates"]
        # Diagnostics run for every verdict, even if the isolated gate job failed.
        assert "needs.acceptance-gates.result" not in closer["if"]
        assert "needs.verifier.outputs.verdict != ''" in closer["if"]
        assert closer["permissions"]["issues"] == "write"
        assert jobs["verifier"]["permissions"]["issues"] == "read"
        assert "closeVerifiedSources" in str(closer)
        assert "includeHeadSha: true" in str(closer)
        assert "closeVerifiedSources({ github, context, core," in str(closer)
        download = next(s for s in closer["steps"] if s["name"] == "Download merge gate results")
        assert "needs.acceptance-gates.result == 'success'" in download["if"]
        assert download["continue-on-error"] is True
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
        ['unverifiable-input+gate+ci', 'UNVERIFIABLE_INPUT'],
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
      const storedPlans = JSON.parse(require('fs').readFileSync('closure-plans/plans.json'));
      assert.deepEqual(storedPlans.map(p=>p.issue_number), [1,2,3]);
      assert.equal(storedPlans[0].plan_error, 'closure-plan-unavailable');
      assert.equal(storedPlans[1].plan_error, 'closure-plan-unavailable');
      assert.equal(storedPlans[2].plan_error, undefined);
    })().catch(error=>{ console.error(error); process.exit(1); });
    """.replace("CLOSURE", json.dumps(str(ROOT / ".github/scripts/verifier_closure.js"))).replace(
        "SCRIPT", script
    )
    subprocess.run(
        ["node", "-e", harness], cwd=tmp_path, check=True, capture_output=True, text=True
    )


def test_authored_workflow_closes_both_gate_sources_and_logs_refusals(tmp_path):
    """Execute production extraction, isolated gates and both caller closure scripts."""
    import hashlib
    import json
    import os
    import subprocess
    import sys

    merge_sha = "a" * 40
    plans = []
    for number, criterion in [(1, "`make gate` passes"), (2, "The feature works")]:
        markdown = f"## Acceptance Criteria\n- [ ] {criterion}\n"
        plans.append(
            {
                "issue_number": number,
                "repository": "owner/repo",
                "pr_number": 5,
                "head_sha": merge_sha,
                "source_hash": hashlib.sha256(markdown.encode()).hexdigest(),
                "markdown": markdown,
            }
        )
    plans.append(
        {
            "issue_number": 3,
            "repository": "owner/repo",
            "pr_number": 5,
            "plan_error": "closure-plan-unavailable",
        }
    )
    (tmp_path / ".workflows-lib").symlink_to(ROOT, target_is_directory=True)
    (tmp_path / "gate-runner").symlink_to(ROOT, target_is_directory=True)
    (tmp_path / "closure-plans").mkdir()
    (tmp_path / "closure-results").mkdir()
    (tmp_path / "acceptance-head").mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    make = binaries / "make"
    make.write_text('#!/bin/sh\n[ "$1" = gate ] || exit 1\ntouch named-gate-ran\n')
    make.chmod(0o755)
    env = os.environ | {
        "PATH": f"{binaries}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path / "runner-temp"),
    }
    (tmp_path / "runner-temp").mkdir()
    reusable = yaml.safe_load((ROOT / ".github/workflows/reusable-agents-verifier.yml").read_text())
    extraction = next(
        s["run"]
        for s in reusable["jobs"]["verifier"]["steps"]
        if s["name"] == "Extract exact acceptance command sets"
    )
    plan_path = tmp_path / "closure-plans/plans.json"
    plan_path.write_text(json.dumps(plans))
    subprocess.run(
        ["bash", "-eu", "-c", extraction.replace("python3 -", f"{sys.executable} -")],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    extracted = json.loads(plan_path.read_text())
    assert [p["gate_source"] for p in extracted if not p.get("plan_error")] == [
        "acceptance-commands",
        "required-ci",
    ]

    for relative in [
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
    ]:
        jobs = yaml.safe_load((ROOT / relative).read_text())["jobs"]
        gate = next(s["run"] for s in jobs["acceptance-gates"]["steps"] if "run" in s)
        subprocess.run(
            ["bash", "-eu", "-c", gate.replace("python3 -", f"{sys.executable} -")],
            cwd=tmp_path,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        assert (tmp_path / "acceptance-head/named-gate-ran").is_file()
        gate_results = json.loads((tmp_path / "closure-results.json").read_text())
        assert gate_results[0]["results"][0]["exit_code"] == 0
        assert gate_results[1]["results"] == []
        (tmp_path / "closure-results/closure-results.json").write_text(json.dumps(gate_results))
        close = next(s for s in jobs["close-sources"]["steps"] if "script" in s.get("with", {}))
        harness = r"""
        const fs = require('fs');
        const [script, closurePath, ci] = JSON.parse(process.argv[1]);
        const plans = JSON.parse(fs.readFileSync('closure-plans/plans.json'));
        const messages = [], comments = [], closed = [];
        const core = {info: message => messages.push(message)};
        const context = {repo: {owner: 'owner', repo: 'repo'}};
        const github = {rest: {
          pulls: {get: async () => ({data: {merged: true, merge_commit_sha: 'a'.repeat(40)}})},
          issues: {
            get: async ({issue_number}) => ({data: {state: 'open', body: plans.find(p=>p.issue_number===issue_number).markdown}}),
            createComment: async args => comments.push(args.body),
            update: async args => closed.push(args.issue_number),
          },
        }};
        const fakeRequire = name => {
          if (name === 'fs') return fs;
          if (name.endsWith('/verifier_closure.js')) return require(closurePath);
          if (name.endsWith('/verifier_ci_query.js')) return {queryVerifierCiResults: async options => {
            require('assert').equal(options.targetSha, 'a'.repeat(40));
            require('assert').equal(options.includeHeadSha, true);
            require('assert').deepEqual(options.workflows, JSON.parse(process.env.CI_WORKFLOWS).map(workflow_id=>({workflow_id})));
            return ci;
          }};
          throw Error(name);
        };
        (async () => {
          await Object.getPrototypeOf(async function(){}).constructor('require','github','context','core',script)(fakeRequire,github,context,core);
          process.stdout.write(JSON.stringify({closed, comments, messages}));
        })().catch(error=>{console.error(error);process.exit(1)});
        """
        for ci in [
            [{"head_sha": merge_sha, "conclusion": "success"}],
            [],
            [{"head_sha": "b" * 40, "conclusion": "success"}],
        ]:
            output = subprocess.run(
                [
                    "node",
                    "-e",
                    harness,
                    json.dumps(
                        [
                            close["with"]["script"],
                            str(ROOT / ".github/scripts/verifier_closure.js"),
                            ci,
                        ]
                    ),
                ],
                cwd=tmp_path,
                env=env
                | {
                    **close["env"],
                    "VERDICT": "UNVERIFIABLE_INPUT",
                    "TARGET_SHA": merge_sha,
                    "PR_NUMBER": "5",
                },
                check=True,
                capture_output=True,
                text=True,
            )
            receipt = json.loads(output.stdout)
            assert "owner/repo#3: kept open — closure-plan-unavailable" in receipt["messages"]
            if ci and ci[0]["head_sha"] == merge_sha:
                assert receipt["closed"] == [1, 2]
                assert "gate_source=acceptance-commands" in receipt["comments"][0]
                assert "gate_source=required-ci" in receipt["comments"][1]
            else:
                assert receipt["closed"] == []
                assert receipt["comments"] == []
                assert all(
                    "kept open — gate-ci-missing-stale-or-not-successful" in line
                    for line in receipt["messages"][:2]
                )
