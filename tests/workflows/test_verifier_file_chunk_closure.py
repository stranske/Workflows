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
