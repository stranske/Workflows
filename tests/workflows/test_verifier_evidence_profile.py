"""Bounded recovery inputs must widen inspection without weakening coverage."""

import os
import re
import subprocess
import sys
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


@pytest.mark.parametrize("evidence_chars,complete", [(315_891, True), (524_289, False)])
def test_expanded_profile_retains_captured_evidence_with_a_finite_ceiling(
    tmp_path, monkeypatch, evidence_chars, complete
):
    from scripts.langchain import pr_verifier

    output = tmp_path / "env"
    subprocess.run(
        ["bash", "-c", profile_step()["run"]],
        env={
            **os.environ,
            "VERIFIER_EVIDENCE_PROFILE": "expanded",
            "VERIFIER_MODE": "compare",
            "GITHUB_ENV": str(output),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    for line in output.read_text().splitlines():
        name, value = line.split("=", 1)
        monkeypatch.setenv(name, value)
    prefix = (
        "## Acceptance evidence\n\n- Overall retrieval status: **present**\n"
        "- PR comments: **present**\n\n"
    )
    sentinel = "FINAL-BYTE-VALIDATION-RECEIPT"
    evidence = prefix + "x" * (evidence_chars - len(prefix) - len(sentinel)) + sentinel
    context = (
        "# Verifier context\n\n## CI Information\n\nCI passed.\n\n"
        "## Plan sources (scope, tasks, acceptance)\n\n"
        "### Acceptance Criteria\n- Test evidence must be in a PR comment.\n\n"
        + evidence
        + "\n\n## PR Diff Summary\n\nOne changed file.\n"
    )
    diff = "diff --git a/example.py b/example.py\n--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old\n+new\n"
    inputs = pr_verifier.build_prompt_inputs(context, diff)
    assert inputs.coverage.acceptance_evidence == ("complete" if complete else "truncated")
    assert inputs.coverage.sufficient is complete
    assert (sentinel in inputs.context_block) is complete


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
        env={
            **os.environ,
            "VERIFIER_EVIDENCE_PROFILE": profile,
            "VERIFIER_MODE": "compare",
            "GITHUB_ENV": str(output),
        },
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
            "VERIFIER_ACCEPTANCE_EVIDENCE_BUDGET_TOKENS": "131072",
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


@pytest.mark.parametrize("profile", [None, "standard", "expanded"])
@pytest.mark.parametrize("consumer", [False, True])
def test_only_expanded_contract_fingerprint_changes(profile, consumer):
    path = (
        "templates/consumer-repo/.github/workflows/agents-verifier.yml"
        if consumer
        else ".github/workflows/reusable-agents-verifier.yml"
    )
    text = Path(path).read_text()
    expression = re.search(r"['\"]evidence_contract['\"]:\s*(\(.*?\)),", text, re.S)[1]
    env = {**os.environ}
    name = "VERIFY_EVIDENCE_PROFILE" if consumer else "VERIFIER_EVIDENCE_PROFILE"
    env.pop(name, None)
    # The reusable worker's job env always resolves an absent input to standard.
    if profile is not None or not consumer:
        env[name] = profile or "standard"
    result = subprocess.run(
        [sys.executable, "-c", f"import os\nprint({expression})"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == (
        "bounded-native-capacity-v7" if profile == "expanded" else "bounded-native-capacity-v2"
    )


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


@pytest.mark.parametrize(
    "mode", ["checkbox", "typo", "", "EVALUATE", "compare ", "$(printf unsafe)"]
)
def test_expanded_checkbox_rejects_before_any_generation(tmp_path, mode):
    output = tmp_path / "env"
    result = subprocess.run(
        ["bash", "-c", profile_step()["run"]],
        env={
            **os.environ,
            "VERIFIER_EVIDENCE_PROFILE": "expanded",
            "VERIFIER_MODE": mode,
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


@pytest.mark.parametrize("step_id", ["llm_evaluate", "llm_compare"])
@pytest.mark.parametrize("profile", ["standard", "expanded"])
def test_selected_profile_reaches_python_process(tmp_path, step_id, profile):
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    job = workflow["jobs"]["verifier"]
    select = next(
        s for s in job["steps"] if s.get("name") == "Select bounded verifier evidence profile"
    )
    invoke = next(s for s in job["steps"] if s.get("id") == step_id)
    env = dict(os.environ)
    env.pop("VERIFIER_EVIDENCE_PROFILE", None)
    env["GITHUB_ENV"] = str(tmp_path / "github-env")

    def step_env(step):
        resolved = {**env, **job.get("env", {}), **step.get("env", {})}
        for key, value in resolved.items():
            if "${{" in value:
                resolved[key] = (
                    profile
                    if value == "${{ inputs.evidence_profile }}"
                    else step_id.removeprefix("llm_") if value == "${{ inputs.mode }}" else ""
                )
        return resolved

    selected = subprocess.run(
        ["bash", "-c", select["run"]], env=step_env(select), capture_output=True, text=True
    )
    assert selected.returncode == 0, selected.stderr
    if Path(env["GITHUB_ENV"]).exists():
        env.update(line.split("=", 1) for line in Path(env["GITHUB_ENV"]).read_text().splitlines())
    # Execute the authored invocation shell; intercept only its Python program.
    binary = tmp_path / "python"
    binary.write_text('#!/bin/sh\nprintf "%s" "${VERIFIER_EVIDENCE_PROFILE:-missing}"\n')
    binary.chmod(0o755)
    env["PATH"] = str(tmp_path) + os.pathsep + env["PATH"]
    script = re.sub(r"\$\{\{.*?\}\}", "", invoke["run"].split("# Parse result", 1)[0])
    run = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=step_env(invoke), capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    result = tmp_path / ("evaluation.json" if step_id == "llm_evaluate" else "comparison.json")
    assert result.read_text() == profile


@pytest.mark.parametrize("mode", ["evaluate", "compare"])
def test_capacity_receipt_upload_survives_failed_generation(mode):
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    uploads = [
        step
        for step in workflow["jobs"]["verifier"]["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
        and "verifier-capacity-checks.jsonl" in step["with"].get("path", "")
    ]
    matching = [step for step in uploads if f"inputs.mode == '{mode}'" in step.get("if", "")]
    assert matching, f"capacity receipt has no upload for {mode}"
    assert all("always()" in step["if"] for step in matching)
    assert all("outcome" not in step["if"] and "has_results" not in step["if"] for step in matching)


def test_evaluate_capacity_upload_uses_immutable_action():
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    upload = next(
        step
        for step in workflow["jobs"]["verifier"]["steps"]
        if step.get("name") == "Upload evaluation capacity receipts"
    )
    assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload["uses"])


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("$(printf MODE_INTERPOLATION_EXECUTED >&2)", "pass"),
        ('evaluate"; printf MODE_INTERPOLATION_EXECUTED >&2; #', "pass"),
        ("evaluate", "pass"),
        ("compare", "concerns"),
        ("checkbox", "pass"),
    ],
)
def test_unified_mode_is_literal_environment_transport(tmp_path, mode, expected):
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(
        s for s in workflow["jobs"]["verifier"]["steps"] if s.get("id") == "unified_verdict"
    )
    values = {
        "inputs.mode": mode,
        "steps.verdict.outputs.verdict": "pass",
        "steps.llm_evaluate.outputs.verdict": "pass",
        "steps.llm_compare.outputs.verdict": "concerns",
        "steps.context.outputs.ci_failed": "false",
    }

    def render(value):
        return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values.get(m[1], ""), value)

    env = {**os.environ, "GITHUB_OUTPUT": str(tmp_path / "output")}
    env.update({key: render(value) for key, value in step.get("env", {}).items()})
    run = subprocess.run(
        ["bash", "-c", render(step["run"])], env=env, capture_output=True, text=True
    )
    assert run.returncode == 0, run.stderr
    assert "MODE_INTERPOLATION_EXECUTED" not in run.stdout + run.stderr
    assert Path(env["GITHUB_OUTPUT"]).read_text().strip() == f"verdict={expected}"


@pytest.mark.parametrize(
    "mode",
    [
        "$(printf MODE_INTERPOLATION_EXECUTED >&2)",
        'checkbox"; printf MODE_INTERPOLATION_EXECUTED >&2; #',
        "checkbox",
        "compare",
    ],
)
def test_auth_mode_is_literal_environment_transport(mode):
    workflow = yaml.load(
        Path(".github/workflows/reusable-agents-verifier.yml").read_text(), Loader=yaml.BaseLoader
    )
    step = next(
        s
        for s in workflow["jobs"]["verifier"]["steps"]
        if s.get("name") == "Validate Codex auth for checkbox/compare modes"
    )
    values = {"inputs.mode": mode, "secrets.CODEX_AUTH_JSON": ""}

    def render(value):
        return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", lambda m: values.get(m[1], ""), value)

    env = {"PATH": os.environ.get("PATH", "")}
    env.update({key: render(value) for key, value in step.get("env", {}).items()})
    run = subprocess.run(
        ["bash", "-c", render(step["run"])], env=env, capture_output=True, text=True
    )
    assert run.returncode == 1
    assert not run.stderr
    assert f"mode '{mode}'" in run.stdout


def test_capacity_docs_do_not_assume_absent_sdk_profiles():
    contract = Path("docs/ops/CONSUMER_REPO_MAINTENANCE.md").read_text()
    assert "SDK-bundled profiles vary by installed version" in contract
    assert "selected Terra/Sonnet models currently have no capacity facts" not in contract


def test_capacity_docs_keep_input_and_context_bounds_independent():
    contract = Path("docs/ops/CONSUMER_REPO_MAINTENANCE.md").read_text()
    assert "exceeds the input bound. This is conservative" not in contract
    assert "input <= input limit, input + actual output <= context limit" in contract


def test_workflow_inventory_names_current_expanded_fingerprint():
    inventory = Path("docs/ci/WORKFLOWS.md").read_text()
    workflow = Path(".github/workflows/reusable-agents-verifier.yml").read_text()
    assert "`bounded-native-capacity-v7`" in inventory
    assert "bounded-native-capacity-v7" in workflow


def test_workflow_guide_distinguishes_verifier_checkout_tokens():
    guide = Path("docs/WORKFLOW_GUIDE.md").read_text()
    assert "App token is restricted to the caller checkout" in guide
    assert "Workflows scripts checkout uses `github.token`" in guide
