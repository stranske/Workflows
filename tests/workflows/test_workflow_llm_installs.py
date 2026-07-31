from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

WORKFLOWS_DIR = Path(".github/workflows")
AUTO_PILOT = WORKFLOWS_DIR / "agents-auto-pilot.yml"
ISSUE_OPTIMIZER = WORKFLOWS_DIR / "agents-issue-optimizer.yml"
VERIFIER = WORKFLOWS_DIR / "reusable-agents-verifier.yml"
VERIFY_TO_ISSUE = WORKFLOWS_DIR / "agents-verify-to-issue-v2.yml"
REUSABLE_CODEX_RUN = WORKFLOWS_DIR / "reusable-codex-run.yml"
REUSABLE_CLAUDE_RUN = WORKFLOWS_DIR / "reusable-claude-run.yml"
NEEDS_HUMAN_COMMENT = Path("agents/codex-1447.md")
REFERENCE_PACK_ACTION = Path(".github/actions/agent-reference-packs/action.yml")
REFERENCE_PACK_RUNNER_USES = "./.workflows-lib/.github/actions/agent-reference-packs"
REFERENCE_PACK_FIXTURES = Path("tests/workflows/fixtures/reference_packs")
MIN_CODEX_CLI_BY_RUN_MODEL = {
    "gpt-5.5": (0, 125, 0),
    "gpt-5.4": (0, 125, 0),
}
ACTIONS_CACHE_V6_REF = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
LLM_REGISTRY_MODULE = "tools/llm_registry.py"
LLM_CONFIG_PATHS = (Path("config/llm_slots.json"), Path("config/model_registry.json"))
LANGCHAIN_ENTRYPOINT_DIR = "scripts/langchain"
VERIFY_TO_NEW_PR = WORKFLOWS_DIR / "agents-verify-to-new-pr.yml"
KNOWN_LLM_CLIENT_WORKFLOWS = (VERIFIER, VERIFY_TO_ISSUE, VERIFY_TO_NEW_PR)


def _load_text(path: Path) -> str:
    assert path.exists(), f"Workflow {path.name} must exist"
    return path.read_text(encoding="utf-8")


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(_load_text(path))


def _parse_version_tuple(value: str) -> tuple[int, int, int]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    assert match, f"Could not parse semantic version from: {value!r}"
    return tuple(int(part) for part in match.groups())


def _workflow_call_inputs(workflow: dict) -> dict:
    on_block = workflow.get("on") or workflow.get(True)
    return on_block["workflow_call"]["inputs"]


def _resolve_codex_fallback_models(resolve_step: dict, inputs: dict) -> list[str]:
    fallback_value = resolve_step["env"]["FALLBACK_CODEX_MODELS"]
    input_expression = "${{ inputs.codex_fallback_models }}"
    if fallback_value == input_expression:
        fallback_value = inputs["codex_fallback_models"]["default"]
    return fallback_value.split()


def _codex_run_model_candidates(resolve_step: dict, inputs: dict) -> list[str]:
    default_model = resolve_step["env"]["DEFAULT_CODEX_MODEL"]
    fallback_models = _resolve_codex_fallback_models(resolve_step, inputs)
    return [default_model, *fallback_models]


def _assert_pinned_install(text: str, expected: str, name: str, minimum: int = 1) -> None:
    count = text.count(expected)
    assert (
        count >= minimum
    ), f"{name} must include `{expected}` at least {minimum} time(s); found {count}."


def _assert_no_floating_langchain(text: str, name: str) -> None:
    # Match lines that do `pip install ... langchain*` without -r (requirements file).
    # Lines using `pip install -r <file>` are safe even if the requirements
    # file itself is named with "langchain" in the path.
    pattern = re.compile(
        r"^[^#]*\bpip\s+install\b(?!.*\s+-r\s).*\blangchain[\w-]*",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    assert match is None, f"{name} contains floating langchain install: `{match.group(0).strip()}`"


def _iter_steps(workflow: dict) -> list[dict]:
    steps: list[dict] = []
    for job in (workflow.get("jobs") or {}).values():
        job_steps = job.get("steps") or []
        if isinstance(job_steps, list):
            steps.extend(step for step in job_steps if isinstance(step, dict))
    return steps


def _sparse_checkout_paths(step: dict) -> list[str]:
    raw = str((step.get("with") or {}).get("sparse-checkout", ""))
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _workflows_library_checkout_steps(workflow: dict) -> list[dict]:
    steps = []
    for step in _iter_steps(workflow):
        with_block = step.get("with") or {}
        if with_block.get("repository") == "stranske/Workflows" and "sparse-checkout" in with_block:
            steps.append(step)
    return steps


def _discover_llm_client_workflows() -> list[Path]:
    """Workflows that vendor `tools` and then run the LangChain client from it.

    Discovery rather than an explicit list: any future workflow that vendors the
    client inherits the config-vendoring requirement automatically.
    """
    matches = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")) + sorted(WORKFLOWS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        if LANGCHAIN_ENTRYPOINT_DIR not in text:
            continue
        workflow = yaml.safe_load(text)
        if not isinstance(workflow, dict):
            continue
        if any(
            "tools" in _sparse_checkout_paths(step)
            for step in _workflows_library_checkout_steps(workflow)
        ):
            matches.append(path)
    return matches


def _find_step_by_name(workflow: dict, step_name: str) -> dict:
    for step in _iter_steps(workflow):
        if step.get("name") == step_name:
            return step
    raise AssertionError(f"Missing workflow step: {step_name}")


def _reference_pack_action_script() -> str:
    action = _load_workflow(REFERENCE_PACK_ACTION)
    step = _find_step_by_name(
        {"jobs": {"action": {"steps": action["runs"]["steps"]}}},
        "Validate and materialize reference packs",
    )
    return str(step.get("run", ""))


def _assert_pip_cache(workflow: dict, hash_path: str, name: str) -> None:
    expected_hash = f"hashFiles('{hash_path}')"
    expected_hash_alt = f'hashFiles("{hash_path}")'
    for step in _iter_steps(workflow):
        if step.get("uses") != ACTIONS_CACHE_V6_REF:
            continue
        with_block = step.get("with") or {}
        key = str(with_block.get("key", ""))
        if (expected_hash in key or expected_hash_alt in key) and "python-version" in key:
            return
    raise AssertionError(
        f"{name} must include {ACTIONS_CACHE_V6_REF} step with key using python-version and hashFiles('{hash_path}')."
    )


def _materialize_reference_pack_directories(
    workspace: Path,
    checkout_plan: list[dict],
    fixture_repo_root: Path,
) -> None:
    for entry in checkout_plan:
        pack_name = entry["name"]
        checkout_path = workspace / entry["checkout_path"]
        source_root = fixture_repo_root / pack_name
        assert source_root.exists(), f"Fixture source missing for pack: {pack_name}"
        checkout_path.mkdir(parents=True, exist_ok=True)

        for rel_path in entry["paths"]:
            source = source_root / rel_path
            destination = checkout_path / rel_path
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)


def _render_prompt_with_assemble_step(
    tmp_path: Path,
    workflow: dict,
    *,
    base_prompt_text: str,
    appendix: str = "",
    mode: str = "autofix",
    pr_number: str = "",
    orchestrator_skill_summary_path: str = "",
    agents_text: str | None = None,
) -> str:
    assemble_step = _find_step_by_name(workflow, "Assemble prompt")
    run_script = str(assemble_step.get("run", ""))
    base_prompt = tmp_path / "base_prompt.md"
    base_prompt.write_text(base_prompt_text, encoding="utf-8")
    if agents_text is not None:
        (tmp_path / "AGENTS.md").write_text(agents_text, encoding="utf-8")
    github_output = tmp_path / "github_output.txt"
    github_output.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "BASE_PROMPT": str(base_prompt),
            "APPENDIX": appendix,
            "PR_NUMBER": pr_number,
            "MODE": mode,
            "GITHUB_OUTPUT": str(github_output),
            "GITHUB_WORKSPACE": str(Path.cwd()),
            "ORCHESTRATOR_SKILL_SUMMARY_PATH": orchestrator_skill_summary_path,
        }
    )

    result = subprocess.run(
        ["bash", "-c", run_script],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr

    output_file = None
    for line in github_output.read_text(encoding="utf-8").splitlines():
        if line.startswith("file="):
            output_file = line.split("=", 1)[1].strip()
            break
    assert output_file, "Assemble prompt step must write file=<path> to GITHUB_OUTPUT"

    return (tmp_path / output_file).read_text(encoding="utf-8")


def test_agents_auto_pilot_llm_install_is_pinned() -> None:
    text = _load_text(AUTO_PILOT)
    _assert_pinned_install(
        text,
        "python -m pip install -r tools/requirements-llm.txt",
        AUTO_PILOT.name,
    )
    _assert_no_floating_langchain(text, AUTO_PILOT.name)


def test_agents_issue_optimizer_llm_install_is_pinned() -> None:
    text = _load_text(ISSUE_OPTIMIZER)
    _assert_pinned_install(
        text,
        "python -m pip install -r tools/requirements-llm.txt",
        ISSUE_OPTIMIZER.name,
    )
    _assert_no_floating_langchain(text, ISSUE_OPTIMIZER.name)


def test_agents_auto_pilot_pip_cache_is_configured() -> None:
    if os.environ.get("AGENT_ENV", "agent-standard") != "agent-high-privilege":
        pytest.skip("needs-human: workflow updates require agent-high-privilege")
    workflow = _load_workflow(AUTO_PILOT)
    _assert_pip_cache(workflow, "tools/requirements-llm.txt", AUTO_PILOT.name)


def test_reusable_agents_verifier_llm_install_is_pinned_for_modes() -> None:
    text = _load_text(VERIFIER)
    _assert_pinned_install(
        text,
        "pip install -r .workflows-lib/tools/requirements-llm.txt",
        VERIFIER.name,
        minimum=2,
    )
    _assert_no_floating_langchain(text, VERIFIER.name)


def test_reusable_agents_verifier_pip_cache_is_configured() -> None:
    if os.environ.get("AGENT_ENV", "agent-standard") != "agent-high-privilege":
        pytest.skip("needs-human: workflow updates require agent-high-privilege")
    workflow = _load_workflow(VERIFIER)
    _assert_pip_cache(workflow, ".workflows-lib/tools/requirements-llm.txt", VERIFIER.name)


def test_llm_client_workflow_discovery_covers_the_known_verifier_surfaces() -> None:
    discovered = set(_discover_llm_client_workflows())
    missing = [path.name for path in KNOWN_LLM_CLIENT_WORKFLOWS if path not in discovered]
    assert not missing, (
        f"Discovery no longer sees {missing}; the config-vendoring guard below would "
        "silently stop covering them."
    )


@pytest.mark.parametrize(
    "workflow_path", _discover_llm_client_workflows(), ids=lambda path: path.name
)
def test_llm_workflows_vendor_the_model_registry_config(workflow_path: Path) -> None:
    workflow = _load_workflow(workflow_path)
    checkouts = _workflows_library_checkout_steps(workflow)
    assert checkouts, f"{workflow_path.name} must sparse-checkout stranske/Workflows"

    vendors_tools = False
    for step in checkouts:
        paths = _sparse_checkout_paths(step)
        if "tools" not in paths:
            continue
        vendors_tools = True
        missing = [entry for entry in ("config",) if entry not in paths]
        assert not missing, (
            f"{workflow_path.name} vendors `tools` but not {missing}; "
            f"{LLM_REGISTRY_MODULE} resolves {', '.join(str(p) for p in LLM_CONFIG_PATHS)} "
            "relative to the vendored tree, so every judge slot resolves to no model and "
            'compare mode reports "available families: none".'
        )

    assert vendors_tools, f"{workflow_path.name} must vendor `tools` for the LLM client"


def test_bundled_llm_config_resolves_two_cross_family_judges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots_path, registry_path = LLM_CONFIG_PATHS
    for config_path in LLM_CONFIG_PATHS:
        assert config_path.is_file(), f"Vendored LLM config {config_path} must exist"

    from tools import llm_registry
    from tools.llm_registry import load_slot_config

    # Pin resolution to the bundled files so an ambient override cannot make this pass.
    monkeypatch.delenv(llm_registry.ENV_SLOT_CONFIG, raising=False)
    monkeypatch.delenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, raising=False)
    monkeypatch.setattr(llm_registry, "DEFAULT_SLOT_CONFIG_PATH", slots_path.resolve())
    monkeypatch.setattr(llm_registry, "DEFAULT_MODEL_REGISTRY_CONFIG_PATH", registry_path.resolve())

    families = {slot.provider for slot in load_slot_config() if slot.model}
    assert len(families) >= 2, (
        "Compare mode needs two cross-family judges; the bundled config resolved "
        f"models for {sorted(families) or 'no provider'}."
    )


def test_reusable_codex_run_persists_refreshed_auth_bundle_with_app_token() -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    step = _find_step_by_name(workflow, "Persist refreshed Codex auth secret")

    assert step.get("id") == "persist_codex_auth"
    assert "steps.codex_auth.outcome == 'success'" in str(step.get("if", ""))
    assert step.get("continue-on-error") is True

    env = step.get("env") or {}
    assert env.get("GH_TOKEN") == "${{ steps.run_base.outputs.push_token }}"
    assert env.get("INITIAL_AUTH_SHA") == "${{ steps.codex_auth.outputs.auth_sha }}"

    run_script = str(step.get("run", ""))
    required_snippets = [
        'echo "reason=no-app-token" >> "$GITHUB_OUTPUT"',
        'echo "reason=missing-auth-file" >> "$GITHUB_OUTPUT"',
        'echo "reason=unchanged" >> "$GITHUB_OUTPUT"',
        'gh secret set CODEX_AUTH_JSON --repo "$GITHUB_REPOSITORY" < "$source_auth"',
        'echo "reason=updated" >> "$GITHUB_OUTPUT"',
    ]
    missing = [snippet for snippet in required_snippets if snippet not in run_script]
    assert not missing, f"Persist step missing required snippets: {missing}"


def test_reusable_codex_run_prefers_gpt_55_with_non_codex_fallback() -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    inputs = _workflow_call_inputs(workflow)
    resolve_step = _find_step_by_name(workflow, "Resolve Codex run model")
    run_step = _find_step_by_name(workflow, "Run Codex")

    assert inputs["codex_model"]["default"] == "gpt-5.5"
    assert inputs["codex_cli_version"]["default"] == "0.125.0"
    assert resolve_step.get("id") == "codex_model"
    assert resolve_step["env"]["DEFAULT_CODEX_MODEL"] == "gpt-5.5"
    assert inputs["codex_fallback_models"]["default"] == "gpt-5.4"
    assert resolve_step["env"]["FALLBACK_CODEX_MODELS"] == "${{ inputs.codex_fallback_models }}"
    assert "fallback-unsupported-chatgpt-codex-model" in resolve_step["run"]
    assert "*-codex*" in resolve_step["run"]
    assert 'printf \'%s\\n\' "$model" "${fallback_models[@]}"' in resolve_step["run"]
    assert 'printf \'%s\\n\' "$DEFAULT_CODEX_MODEL" "${fallback_models[@]}"' in resolve_step["run"]
    assert "awk 'NF && !seen[$0]++" in resolve_step["run"]
    assert "gpt-5.3-codex" not in resolve_step["run"]

    assert "CODEX_MODEL_CANDIDATES" in run_step["env"]
    assert 'for codex_model in "${codex_models[@]}"; do' in run_step["run"]
    assert '--model "$codex_model"' in run_step["run"]
    assert "runtime-fallback-model-unavailable" in run_step["run"]


def test_reusable_codex_run_model_cli_compatibility_contract() -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    inputs = _workflow_call_inputs(workflow)
    resolve_step = _find_step_by_name(workflow, "Resolve Codex run model")

    installed_cli = _parse_version_tuple(inputs["codex_cli_version"]["default"])
    candidates = _codex_run_model_candidates(resolve_step, inputs)
    unreviewed_models = [model for model in candidates if model not in MIN_CODEX_CLI_BY_RUN_MODEL]
    assert not unreviewed_models, (
        "Reusable Codex run model candidates need an explicit reviewed minimum CLI mapping: "
        + ", ".join(unreviewed_models)
    )

    for model in candidates:
        minimum_cli = MIN_CODEX_CLI_BY_RUN_MODEL[model]
        assert installed_cli >= minimum_cli, (
            f"Codex run model {model} requires @openai/codex >= {minimum_cli}, "
            f"but reusable-codex-run.yml defaults to {installed_cli}."
        )


def test_workflow_llm_needs_human_comment_documents_blocker() -> None:
    text = _load_text(NEEDS_HUMAN_COMMENT)
    required_phrases = [
        "Label: needs-human",
        ".github/workflows/agents-auto-pilot.yml",
        ".github/workflows/agents-issue-optimizer.yml",
        ".github/workflows/reusable-agents-verifier.yml",
        ACTIONS_CACHE_V6_REF,
        "tools/requirements-llm.txt",
        ".workflows-lib/tools/requirements-llm.txt",
        "langchain",
        "agent-high-privilege",
    ]
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing, f"needs-human comment missing: {', '.join(missing)}"


def test_valid_reference_pack_config_materializes_populated_directories(tmp_path: Path) -> None:
    fixture_config = REFERENCE_PACK_FIXTURES / "valid_reference_packs.json"
    fixture_repo_root = REFERENCE_PACK_FIXTURES / "repo_contents"
    assert fixture_config.exists(), "Reference pack fixture config must exist"
    assert fixture_repo_root.exists(), "Reference pack fixture repository data must exist"

    config_dir = tmp_path / ".github"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "reference_packs.json"
    config_path.write_text(fixture_config.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["exists"] is True
    checkout_plan = payload["checkout_plan"]
    assert checkout_plan, "Checkout plan should contain at least one pack for valid config"

    _materialize_reference_pack_directories(tmp_path, checkout_plan, fixture_repo_root)

    expected_file = tmp_path / ".reference" / "trend-streamlit" / "apps" / "streamlit" / "app.py"
    expected_doc = tmp_path / ".reference" / "trend-streamlit" / "langchain" / "README.md"
    assert expected_file.exists()
    assert expected_doc.exists()
    assert expected_file.read_text(encoding="utf-8").strip() == 'print("reference pack app")'


def test_malformed_reference_pack_config_fails_with_parse_error_before_execution(
    tmp_path: Path,
) -> None:
    fixture_config = REFERENCE_PACK_FIXTURES / "malformed_reference_packs.json"
    assert fixture_config.exists(), "Malformed reference pack fixture config must exist"

    config_dir = tmp_path / ".github"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "reference_packs.json"
    config_path.write_text(fixture_config.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Reference packs config error:" in result.stderr
    assert "Malformed JSON" in result.stderr
    assert "line " in result.stderr and " column " in result.stderr
    assert result.stdout.strip() == ""
    assert not (tmp_path / ".reference").exists()


def test_reference_pack_config_missing_required_key_fails_before_execution(
    tmp_path: Path,
) -> None:
    fixture_config = REFERENCE_PACK_FIXTURES / "missing_required_key_reference_packs.json"
    assert fixture_config.exists(), "Missing-key reference pack fixture config must exist"

    config_dir = tmp_path / ".github"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "reference_packs.json"
    config_path.write_text(fixture_config.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/reference_packs.py", "--workspace", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Reference packs config error:" in result.stderr
    assert "Invalid config in" in result.stderr
    assert "repo must be a non-empty string" in result.stderr
    assert result.stdout.strip() == ""
    assert not (tmp_path / ".reference").exists()


def test_reusable_codex_prompt_step_includes_reference_pack_section_when_file_exists(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    reference_text = "# Pack Title\n- item one\n- item two\n"
    reference_path = tmp_path / ".reference" / "REFERENCE_PACKS.md"
    reference_path.parent.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(reference_text, encoding="utf-8")

    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
    )

    assert "## Reference Packs\n" in rendered
    assert "# Pack Title" in rendered
    assert "- item one" in rendered
    assert "- item two" in rendered


def test_reusable_codex_prompt_step_skips_reference_pack_section_when_file_missing(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
    )

    # Missing file should not error and should not add a reference section.
    assert "## Reference Packs\n" not in rendered


def test_reusable_codex_prompt_step_includes_repository_guidance_when_agents_md_exists(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    agents_text = (
        "# AGENTS.md - Workflows Repository Context\n\n"
        "<!-- BEGIN orch-playbook -->\n"
        "## Orchestrator Repo Playbook (stranske/Workflows)\n\n"
        "- Route-weight codemod/refactor issues must produce the requested code or "
        "test change for the closer lane to validate.\n"
        "<!-- END orch-playbook -->\n"
    )

    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
        agents_text=agents_text,
    )

    assert "## Repository Guidance\n" in rendered
    assert "<!-- BEGIN orch-playbook -->" in rendered
    assert "Route-weight codemod/refactor issues" in rendered
    assert "closer lane to validate" in rendered


def test_reusable_codex_prompt_step_skips_repository_guidance_when_agents_md_missing(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
    )

    assert "## Repository Guidance\n" not in rendered


def test_reusable_codex_prompt_step_skips_stale_orchestrator_skill_section_when_file_exists(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    orchestrator_text = (
        "Read and apply the materialized Orchestrator skill files before coordinating work.\n"
    )
    orchestrator_path = tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
    orchestrator_path.parent.mkdir(parents=True, exist_ok=True)
    orchestrator_path.write_text(orchestrator_text, encoding="utf-8")

    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
    )

    assert "## Orchestrator Skill Context\n" not in rendered
    assert "Read and apply the materialized Orchestrator skill files" not in rendered


def test_reusable_codex_prompt_step_includes_active_orchestrator_skill_section(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    orchestrator_text = (
        "Read and apply the materialized Orchestrator skill files before coordinating work.\n"
    )
    orchestrator_path = tmp_path / ".reference" / "ORCHESTRATOR_SKILL.md"
    orchestrator_path.parent.mkdir(parents=True, exist_ok=True)
    orchestrator_path.write_text(orchestrator_text, encoding="utf-8")

    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
        orchestrator_skill_summary_path=str(orchestrator_path),
    )

    assert "## Orchestrator Skill Context\n" in rendered
    assert "Read and apply the materialized Orchestrator skill files" in rendered


def test_reusable_codex_prompt_step_skips_orchestrator_skill_section_when_file_missing(
    tmp_path: Path,
) -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    rendered = _render_prompt_with_assemble_step(
        tmp_path,
        workflow,
        base_prompt_text="Base prompt content\n",
    )

    assert "## Orchestrator Skill Context\n" not in rendered


def test_reusable_codex_workflow_passes_orchestrator_skill_overrides_to_reference_pack_action() -> (
    None
):
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    step = _find_step_by_name(workflow, "Validate and materialize reference packs")
    assert step.get("uses") == REFERENCE_PACK_RUNNER_USES
    with_block = step.get("with") or {}
    assert with_block.get("orchestrator_skill_pack") == "${{ inputs.orchestrator_skill_pack }}"
    assert (
        with_block.get("orchestrator_skill_enabled") == "${{ inputs.orchestrator_skill_enabled }}"
    )


@pytest.mark.parametrize("workflow_path", [REUSABLE_CODEX_RUN, REUSABLE_CLAUDE_RUN])
def test_reusable_runner_workflow_has_reference_pack_validation_step(
    workflow_path: Path,
) -> None:
    workflow = _load_workflow(workflow_path)
    step = _find_step_by_name(workflow, "Validate and materialize reference packs")
    assert step.get("uses") == REFERENCE_PACK_RUNNER_USES
    run_script = _reference_pack_action_script()
    # Shared action must validate config with reference_packs.py
    assert "reference_packs.py" in run_script
    # Shared action must no-op when config file is absent
    assert "reference_packs.json" in run_script
    # Step must be positioned before Assemble prompt
    steps = _iter_steps(workflow)
    step_names = [s.get("name", "") for s in steps]
    ref_idx = step_names.index("Validate and materialize reference packs")
    prompt_idx = step_names.index("Assemble prompt")
    run_step_name = "Run Codex" if workflow_path == REUSABLE_CODEX_RUN else "Run Claude"
    run_idx = step_names.index(run_step_name)
    assert (
        ref_idx < prompt_idx < run_idx
    ), "Reference pack validation must come before Assemble prompt and the runner"


def test_reusable_codex_reference_pack_step_handles_sha_refs() -> None:
    """The materialization script must detect full 40-char hex SHAs and use
    clone+fetch+checkout instead of --branch, and suppress stderr on clone
    commands to avoid leaking tokens."""
    run_script = _reference_pack_action_script()
    # Must detect full 40-char hex SHAs (case-insensitive)
    assert (
        "[0-9a-fA-F]{40}" in run_script
    ), "SHA regex must match full 40-char hex (case-insensitive)"
    # Must use fetch+checkout path for SHAs
    assert (
        "fetch" in run_script and "origin" in run_script
    ), "SHA path must use git fetch origin <sha>"
    assert "--no-checkout" in run_script, "SHA path must clone with --no-checkout"
    # Must suppress stderr on clone to avoid leaking tokens
    assert "stderr=subprocess.DEVNULL" in run_script, "Clone stderr must be suppressed"
    # Must use sparse-checkout reapply (not bare git checkout)
    assert (
        "sparse-checkout" in run_script and "reapply" in run_script
    ), "Must use sparse-checkout reapply instead of bare git checkout"
