from __future__ import annotations

import re
from pathlib import Path

import yaml

SHIM = Path(".github/workflows/agents-model-profile-trial.yml")
RUNNER = Path(".github/workflows/reusable-model-profile-trial.yml")
REGISTRY = Path(".github/agents/registry.yml")
TEMPLATE_REGISTRY = Path("templates/consumer-repo/.github/agents/registry.yml")


def _workflow(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML 1.1 parses the unquoted GitHub Actions `on` key as True.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def test_dispatch_shim_is_single_arm_and_calls_only_pinned_reusable_runner():
    workflow = _workflow(SHIM)
    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "trial_id",
        "request_id",
        "request_hash",
        "trial_run_id",
        "profile_id",
        "packet_hash",
        "launch_ordinal",
        "expected_source_sha",
    }
    assert all(value["required"] is True for value in inputs.values())
    assert inputs["profile_id"]["options"] == [
        "codex-6-astra-high",
        "codex-5.6-sol-high",
        "codex-5.6-terra-high",
        "codex-5.6-luna-high",
    ]
    assert list(workflow["jobs"]) == ["trial"]
    runner_ref = workflow["jobs"]["trial"]["uses"]
    assert re.fullmatch(
        r"stranske/Workflows/\.github/workflows/" r"reusable-model-profile-trial\.yml@[0-9a-f]{40}",
        runner_ref,
    )
    runner_sha = workflow["jobs"]["trial"]["with"]["runner_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", runner_sha)
    assert runner_ref.endswith("@" + runner_sha)
    assert workflow["permissions"] == {"contents": "read"}
    assert "inherit" not in str(workflow["jobs"]["trial"].get("secrets"))


def test_reusable_runner_is_read_only_exact_cli_and_has_no_write_lane():
    workflow = _workflow(RUNNER)
    assert set(workflow["on"]) == {"workflow_call"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["run-single-arm"]
    assert job["permissions"] == {"contents": "read"}
    source = RUNNER.read_text(encoding="utf-8")
    assert "npm ci --prefix runner-src/.github/actions/verifier-codex-cli --ignore-scripts" in source
    assert "--sandbox read-only" in source
    assert 'model_reasoning_effort="high"' in source
    assert "--ignore-user-config" in source
    assert "persist-credentials: false" in source
    assert "expected_source_sha must equal current remote main before auth" in source
    assert "git ls-remote https://github.com/stranske/Workflows.git refs/heads/main" in source
    assert "target-src/scripts/" not in source
    assert "provider_resolved" not in source
    forbidden = (
        "git commit",
        "git push",
        "gh pr",
        "gh issue",
        "create-pull-request",
        "refresh-codex",
        "OPENAI_API_KEY",
        "CLAUDE_API",
    )
    assert not [token for token in forbidden if token in source]


def test_runner_uploads_one_unique_attempt_and_enforces_source_integrity():
    workflow = _workflow(RUNNER)
    steps = workflow["jobs"]["run-single-arm"]["steps"]
    uploads = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert len(uploads) == 1
    assert uploads[0]["with"]["name"] == "${{ steps.artifact.outputs.artifact-name }}"
    source = RUNNER.read_text(encoding="utf-8")
    assert 'artifact_name="model-profile-trial-${PROFILE_ID}-${GITHUB_RUN_ID_VALUE}"' in source
    assert 'artifact_name+="-${GITHUB_RUN_ATTEMPT_VALUE}-${LAUNCH_ORDINAL}"' in source
    assert "source-sha-before" in source
    assert "source-sha-after" in source
    assert "source-manifest-sha256-before" in source
    assert "source-manifest-sha256-after" in source
    assert "git -C target-src status --porcelain --untracked-files=all" in source
    assert "Unable to determine target checkout status" in source
    assert "model_profile_trial_contract.py artifact" in source


def test_runner_uses_separate_pinned_helper_checkout_and_full_action_shas():
    workflow = _workflow(RUNNER)
    steps = workflow["jobs"]["run-single-arm"]["steps"]
    checkouts = [
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert len(checkouts) == 2
    assert checkouts[0]["with"] == {
        "repository": "stranske/Workflows",
        "ref": "${{ inputs.runner_sha }}",
        "path": "runner-src",
        "persist-credentials": False,
    }
    assert checkouts[1]["with"]["path"] == "target-src"
    for step in steps:
        uses = str(step.get("uses", ""))
        if uses.startswith(
            ("actions/checkout@", "actions/setup-python@", "actions/upload-artifact@")
        ):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", uses)

    source = RUNNER.read_text(encoding="utf-8")
    auth_offset = source.index("Configure isolated Codex subscription auth")
    assert "python target-src/" not in source[auth_offset:]
    assert "runner-src/scripts/model_profile_trial_contract.py" in source[auth_offset:]


def test_registry_trial_profiles_share_exact_pinned_read_only_contract():
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    trial = registry["model_profile_trial_contract"]
    assert trial["mode"] == "read-only"
    assert trial["artifact_schema"] == "workflows.model-profile-trial-result/v2"
    assert trial["identity_authority"] == "workflows-read-only-trial-artifact/v2"
    assert (
        trial["collector_identity_authority"]
        == "github-actions-api/workflows-read-only-trial-artifact/v2"
    )
    assert trial["cli_version"] == "0.153.2"
    assert trial["runtime_fallback_allowed"] is False
    assert trial["auxiliary_evaluator_allowed"] is False
    for profile_id in (
        "codex-6-astra-high",
        "codex-5.6-sol-high",
        "codex-5.6-terra-high",
        "codex-5.6-luna-high",
    ):
        profile = registry["execution_profiles"][profile_id]
        assert profile["runner"] == "reusable-model-profile-trial"
        assert profile["runner_ref"] == trial["runner_ref"]
        assert profile["capacity_pool"] == "codex-standard"
        assert profile["reasoning_effort"] == "high"
        assert profile["permission_mode"] == "read-only"
        assert profile["safety"] == "read-only"


def test_consumer_template_registry_matches_authoritative_registry():
    assert TEMPLATE_REGISTRY.read_text(encoding="utf-8") == REGISTRY.read_text(encoding="utf-8")
