"""Guard the source/template delivery boundary for single-use authority claims."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/consumer-repo"


def test_authority_helpers_are_manifested_and_byte_aligned() -> None:
    manifest = yaml.safe_load((ROOT / ".github/sync-manifest.yml").read_text())
    sources = {entry["source"] for entry in manifest["scripts"]}
    for name in (
        "keepalive_authority_state.js",
        "keepalive_challenge_due.js",
        "keepalive_loop.js",
        "keepalive_worker_evidence.js",
        "keepalive_state.js",
    ):
        source = Path(".github/scripts") / name
        assert source.as_posix() in sources
        assert (ROOT / source).read_bytes() == (TEMPLATE / source).read_bytes()


def test_every_sweep_mode_checks_the_ledger_before_signing() -> None:
    for path, modes in (
        (ROOT / ".github/workflows/agents-keepalive-sweep.yml", 1),
        (TEMPLATE / ".github/workflows/agents-keepalive-sweep.yml", 2),
    ):
        text = path.read_text()
        assert text.count("readAuthorityState(") == modes
        assert text.count("state.head_sha !== pr.head.sha") == modes
        assert text.count("generation: dueChallenge.generation") == modes * 2
        assert text.count(".github/scripts/keepalive_authority_state.js") == modes * 2


def test_gate_paths_deny_invalid_claims_and_reporters_can_persist_generation() -> None:
    for path in (
        ROOT / ".github/workflows/agents-keepalive-loop.yml",
        TEMPLATE / ".github/workflows/agents-81-gate-followups.yml",
    ):
        text = path.read_text()
        assert "RAW_AUTHORITY_CHALLENGE_CLAIM" in text
        assert "reason=invalid-signed-authority-challenge" in text
        assert (
            "dispatch_should_run: ${{ steps.runner_dispatch.outputs.should_dispatch || 'false' }}"
            in text
        )
        assert "headSha: process.env.HEAD_SHA" in text
        assert text.count("permission-contents: write") >= 2
        assert text.count("always() && (failure() || cancelled()) &&") >= 2
        assert (
            text.index("Update summary with running status")
            < text.index("Finalize authority challenge after mark-running")
            < text.index("Release prepared challenge after mark-running failure")
        )
        cleanup = text.split("- name: Release prepared challenge after mark-running failure", 1)[1]
        assert "AUTHORITY_CHALLENGE_FINGERPRINT:" in cleanup.split("run: |", 1)[0]
    for path in (
        ROOT / ".github/workflows/agents-keepalive-loop-reporter.yml",
        TEMPLATE / ".github/workflows/agents-keepalive-loop-reporter.yml",
    ):
        workflow = yaml.safe_load(path.read_text())
        assert "concurrency" not in workflow
        assert workflow[True]["workflow_dispatch"]["inputs"]["pr_number"]["required"] is True
        resolver = workflow["jobs"]["resolve-target"]
        assert resolver["permissions"] == {
            "actions": "read",
            "contents": "read",
            "issues": "read",
            "pull-requests": "read",
        }
        assert set(resolver["outputs"]) == {
            "skip",
            "lock_pr_number",
            "pr_number",
            "ordinary_target",
        }
        resolver_names = [step["name"] for step in resolver["steps"]]
        assert resolver_names == [
            "Checkout reporter classifier",
            "Classify unassociated dispatch",
        ]
        resolver_text = path.read_text().split("  report:", 1)[0]
        assert "core.setOutput('lock_pr_number'" in resolver_text
        assert "result.prNumber || associated" in resolver_text
        assert "result.targetSource === 'ordinary-run-name'" in resolver_text
        assert "github.run_id" not in resolver_text
        assert resolver["steps"][0]["with"]["persist-credentials"] is False
        report = workflow["jobs"]["report"]
        assert report["needs"] == "resolve-target"
        report_condition = report["if"]
        assert "needs.resolve-target.result == 'success'" in report_condition
        assert "needs.resolve-target.outputs.skip != 'true'" in report_condition
        assert "needs.resolve-target.outputs.lock_pr_number != ''" in report_condition
        assert "github.event.workflow_run.conclusion != 'success'" in report_condition
        assert "github.event.workflow_run.conclusion != 'skipped'" in report_condition
        report_concurrency = workflow["jobs"]["report"]["concurrency"]
        assert report_concurrency == {
            "group": "keepalive-loop-reporter-${{ needs.resolve-target.outputs.lock_pr_number }}",
            "cancel-in-progress": False,
        }
        steps = workflow["jobs"]["report"]["steps"]
        names = [step["name"] for step in steps]
        assert "Classify unassociated dispatch" not in names
        assert steps[0]["with"]["persist-credentials"] is False
        assert names.index("Checkout keepalive scripts") < names.index(
            "Mint KEEPALIVE_APP reporter token"
        )
        assert "keepalive_reporter_applicability.js" in path.read_text()
        assert "core.setOutput('pr_number'" in path.read_text()
        assert "core.setOutput('ordinary_target'" in path.read_text()
        assert "needs.resolve-target.outputs.pr_number" in path.read_text()
        assert "needs.resolve-target.outputs.ordinary_target" in path.read_text()
        assert "CLASSIFIED_PR_NUMBER:" in path.read_text()
        assert "CLASSIFIED_ORDINARY_TARGET:" in path.read_text()
        assert "state?.running_owner_attempt !== ownerAttempt" in path.read_text()
        assert workflow["permissions"]["contents"].startswith("read")

        assert path.read_text().count("permission-contents: write") == 2
        assert (
            "head_sha: authorityTarget?.state?.head_sha || run.head_sha || ''" in path.read_text()
        )
        assert "authority_owner_attempt:" in path.read_text()
        assert "const ownerAttempt = authorityRecovery.ownerAttempt;" in path.read_text()
        assert "getWorkerExecutionEvidence(" in path.read_text()
        assert "run.head_sha || ''" in path.read_text()
        assert ".github/agents/registry.yml" in path.read_text()
        assert "if (workerEvidence === 'unknown')" in path.read_text()
        assert "retry this reporter" in path.read_text()
        assert "Require PR association for failed originating run" not in path.read_text()
        assert "agent_execution_started: false" not in path.read_text()
        assert "replayReporterAuthority" in path.read_text()
        assert "Authority replay outcomes" in path.read_text()
        assert "context.eventName === 'workflow_dispatch'" in path.read_text()

    applicability = (ROOT / ".github/scripts/keepalive_reporter_applicability.js").read_text()
    assert "run.id}:${run.run_attempt || 1}" in applicability
    assert "projectRecovery = projectRecoveredAuthorityState" in applicability
    assert "const projection = await projectRecovery(" in applicability
    assert "lookupTarget = findAuthorityPrForAttempt" in applicability
    assert "No PR association or authoritative attempt target" in applicability
    assert "async function replayReporterAuthority" in applicability
    assert "readAuthorityStateForReplay" in applicability
    assert "deferred-active-attempt" in applicability
    assert "actions/runs/{run_id}/attempts/{attempt_number}" in applicability
    assert "worker evidence is unknown" in applicability

    authority = (ROOT / ".github/scripts/keepalive_authority_state.js").read_text()
    assert "async function readAuthorityStateForReplay" in authority
    assert "tree?.truncated !== false" in authority

    for sweep in (
        ROOT / ".github/workflows/agents-keepalive-sweep.yml",
        TEMPLATE / ".github/workflows/agents-keepalive-sweep.yml",
    ):
        text = sweep.read_text()
        assert "workflow_id: 'agents-keepalive-loop-reporter.yml'" in text
        assert "authority replay dispatch failed" in text

    for producer in (
        ROOT / ".github/workflows/agents-keepalive-loop.yml",
        TEMPLATE / ".github/workflows/agents-81-gate-followups.yml",
    ):
        run_name = yaml.safe_load(producer.read_text())["run-name"]
        assert "keepalive-dispatch/v2" in run_name
        assert "pr={1}" in run_name
        assert "inputs.pr_number" in run_name
        assert "authority_challenge_claim" in run_name
        assert "authority_challenge_fingerprint" in run_name

    root_reporter = (ROOT / ".github/workflows/agents-keepalive-loop-reporter.yml").read_text()
    assert '"Agents Keepalive Loop"' in root_reporter
    root_steps = yaml.safe_load(root_reporter)["jobs"]["report"]["steps"]
    for name in ("Set up Node.js", "Setup API client"):
        step = next(step for step in root_steps if step["name"] == name)
        assert "needs.resolve-target.outputs.skip != 'true'" in step["if"]
    consumer_reporter = (
        TEMPLATE / ".github/workflows/agents-keepalive-loop-reporter.yml"
    ).read_text()
    consumer_reporter_workflow = yaml.safe_load(consumer_reporter)
    assert "USE_CONSOLIDATED_WORKFLOWS" not in consumer_reporter_workflow["jobs"]["report"]["if"]
    assert '"run_id": int(run.get("id") or 0)' in consumer_reporter
    assert '"run_attempt": int(run.get("run_attempt") or 1)' in consumer_reporter
    consumer_steps = {
        step["name"]: step for step in consumer_reporter_workflow["jobs"]["report"]["steps"]
    }
    assert consumer_steps["Compute state fingerprint"]["if"] == (
        "needs.resolve-target.outputs.skip != 'true'"
    )
    assert consumer_steps["Report unchanged state skip"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'false'"
    )
    assert consumer_steps["Mint KEEPALIVE_APP reporter token"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'true' && "
        "github.event.workflow_run.conclusion != 'success' && "
        "env.KEEPALIVE_APP_ID != '' && env.KEEPALIVE_APP_PRIVATE_KEY != ''"
    )
    assert consumer_steps["Mint WORKFLOWS_APP reporter token"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'true' && "
        "github.event.workflow_run.conclusion != 'success' && "
        "steps.reporter_keepalive_app_token.outputs.token == '' && "
        "env.WORKFLOWS_APP_ID != '' && env.WORKFLOWS_APP_PRIVATE_KEY != ''"
    )
    assert consumer_steps["Require trusted keepalive reporter writer"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'true' && "
        "github.event.workflow_run.conclusion != 'success'"
    )
    assert consumer_steps["Update summary for cancelled/failed runs"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'true' && "
        "github.event.workflow_run.conclusion != 'success'"
    )
    assert consumer_steps["Persist state fingerprint"]["if"] == (
        "steps.fingerprint.outputs.should_run == 'true' && "
        "steps.fingerprint.outputs.current_hash != '' && "
        "steps.update-summary.outcome == 'success'"
    )
