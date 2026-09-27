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
        assert workflow["permissions"]["contents"].startswith("read")
        assert path.read_text().count("permission-contents: write") == 2
        assert (
            "head_sha: authorityTarget?.state?.head_sha || run.head_sha || ''" in path.read_text()
        )
        assert "authority_owner_attempt:" in path.read_text()
        assert "run.id}:${run.run_attempt || 1}" in path.read_text()
        assert "getWorkerExecutionEvidence(" in path.read_text()
        assert ".github/agents/registry.yml" in path.read_text()
        assert "if (workerEvidence === 'unknown')" in path.read_text()
        assert "retry this reporter" in path.read_text()
        assert "projectRecoveredAuthorityState(" in path.read_text()
        assert "findAuthorityPrForAttempt(" in path.read_text()
        assert (
            "if (!prNumber) {\n              try {\n                authorityTarget ="
            in path.read_text()
        )
        assert "No PR association or authoritative attempt target" in path.read_text()
        assert "Require PR association for failed originating run" not in path.read_text()
        assert "agent_execution_started: false" not in path.read_text()

    root_reporter = (ROOT / ".github/workflows/agents-keepalive-loop-reporter.yml").read_text()
    assert '"Agents Keepalive Loop"' in root_reporter
    consumer_reporter = (
        TEMPLATE / ".github/workflows/agents-keepalive-loop-reporter.yml"
    ).read_text()
    assert '"run_id": int(run.get("id") or 0)' in consumer_reporter
    assert '"run_attempt": int(run.get("run_attempt") or 1)' in consumer_reporter
