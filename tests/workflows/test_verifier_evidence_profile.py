"""Bounded recovery inputs must widen inspection without weakening coverage."""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml


def profile_step():
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    return next(
        s
        for s in workflow["jobs"]["verifier"]["steps"]
        if s.get("name") == "Select bounded verifier evidence profile"
    )


@pytest.mark.parametrize("step_id", ["llm_evaluate", "llm_compare"])
@pytest.mark.parametrize(
    "model", ["$(printf INTERPOLATION_EXECUTED)", 'name"; printf EXECUTED; #', "normal-model"]
)
def test_model_inputs_remain_literal_shell_arguments(step_id, model):
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(s for s in workflow["jobs"]["verifier"]["steps"] if s.get("id") == step_id)
    inputs = {"inputs.model": model, "inputs.model2": model, "inputs.provider": "auto"}

    def render(value):
        return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: inputs[m[1]], value)

    env = {**os.environ, "VERIFIER_CONTEXT_PATH": "/absent-context", "VERIFIER_DIFF_PATH": ""}
    for name, value in step["env"].items():
        if value in {"${{ inputs.model }}", "${{ inputs.model2 }}", "${{ inputs.provider }}"}:
            env[name] = render(value)
    if step_id == "llm_evaluate":
        script = step["run"].split("# Build args array", 1)[0]
        script += '\nprintf "%s" "$model"\n'
        expected = model
    else:
        script = step["run"].split("# Run comparison", 1)[0]
        script += '\nprintf "%s\\n" "${args[@]}"\n'
        expected = (
            "\n".join(
                [
                    "--context-file",
                    "/absent-context",
                    "--compare",
                    "--json",
                    "--model",
                    model,
                    "--model2",
                    model,
                ]
            )
            + "\n"
        )
    result = subprocess.run(["bash", "-c", render(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected


@pytest.mark.parametrize("profile", ["standard", "expanded", "invalid", "expanded; touch owned"])
def test_profile_executes_only_fixed_bounded_exports(tmp_path, profile):
    output = tmp_path / "env"
    result = subprocess.run(
        ["bash", "-c", profile_step()["run"]],
        env={**os.environ, "VERIFIER_EVIDENCE_PROFILE": profile, "GITHUB_ENV": str(output)},
        capture_output=True,
        text=True,
    )
    if profile == "standard":
        assert result.returncode == 0 and not output.exists()
    elif profile == "expanded":
        assert result.returncode == 0
        assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
            "VERIFIER_EVIDENCE_COMMENT_LIMIT": "1000",
            "VERIFIER_EVIDENCE_COMMENT_CHARS": "1048576",
            "VERIFIER_EVIDENCE_RUN_LIMIT": "200",
            "VERIFIER_EVIDENCE_ARTIFACT_LIMIT": "400",
            "VERIFIER_EVIDENCE_ARCHIVE_BYTES": "4194304",
            "VERIFIER_EVIDENCE_ENTRY_LIMIT": "80",
            "VERIFIER_EVIDENCE_ARTIFACT_CHARS": "128000",
            "VERIFIER_EVIDENCE_COMMENT_PAGES": "10",
            "VERIFIER_EVIDENCE_RUN_PAGES": "2",
            "VERIFIER_EVIDENCE_ARTIFACT_PAGES": "4",
            "VERIFIER_EVIDENCE_TOTAL_ARCHIVE_BYTES": "33554432",
            "VERIFIER_EVIDENCE_TOTAL_EXTRACT_BYTES": "67108864",
            "VERIFIER_EVIDENCE_TOTAL_ARTIFACT_CHARS": "4194304",
            "VERIFIER_CONTEXT_BUDGET_TOKENS": "16384",
            "VERIFIER_DIFF_BUDGET_TOKENS": "65536",
            "VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS": "65536",
        }
    else:
        assert result.returncode != 0 and not output.exists()


def test_profile_is_propagated_and_fingerprinted():
    for path in [
        ".github/workflows/agents-verifier.yml",
        "templates/consumer-repo/.github/workflows/agents-verifier.yml",
    ]:
        text = Path(path).read_text()
        assert "options: [standard, expanded]" in text
        assert "evidence_profile: ${{ inputs.evidence_profile || 'standard' }}" in text
    template = Path("templates/consumer-repo/.github/workflows/agents-verifier.yml").read_text()
    assert '"evidence_profile": os.environ.get("VERIFY_EVIDENCE_PROFILE", "standard")' in template
    assert '"evidence_contract": "bounded-native-capacity-v2"' in template


def test_input_snapshot_retains_profile_and_every_actual_limit():
    workflow = Path(".github/workflows/reusable-agents-verifier.yml").read_text()
    assert "'evidence_profile': os.environ['VERIFIER_EVIDENCE_PROFILE']" in workflow
    for name in [
        "COMMENT_LIMIT",
        "COMMENT_CHARS",
        "RUN_LIMIT",
        "ARTIFACT_LIMIT",
        "ARCHIVE_BYTES",
        "ENTRY_LIMIT",
        "ARTIFACT_CHARS",
        "BODY_CHARS",
        "COMMENT_PAGES",
        "RUN_PAGES",
        "ARTIFACT_PAGES",
        "TOTAL_ARCHIVE_BYTES",
        "TOTAL_EXTRACT_BYTES",
        "TOTAL_ARTIFACT_CHARS",
    ]:
        assert f"os.environ.get('VERIFIER_EVIDENCE_{name}'" in workflow
    for name in [
        "DIFF_BUDGET_TOKENS",
        "ACCEPTANCE_EVIDENCE_BUDGET_TOKENS",
        "DIFF_MAX_BYTES",
        "DIFF_MAX_CHARS",
        "CONTEXT_BUDGET_TOKENS",
    ]:
        assert f"os.environ.get('VERIFIER_{name}'" in workflow


def test_expanded_checkbox_rejects_before_any_generation(tmp_path):
    output = tmp_path / "env"
    result = subprocess.run(
        ["bash", "-c", profile_step()["run"]],
        env={
            **os.environ,
            "VERIFIER_EVIDENCE_PROFILE": "expanded",
            "VERIFIER_MODE": "checkbox",
            "GITHUB_ENV": str(output),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output.exists()
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(s for s in workflow["jobs"]["verifier"]["steps"] if s.get("id") == "codex")
    assert "inputs.evidence_profile != 'expanded'" in step["if"]
