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
VERIFIER = WORKFLOWS_DIR / "reusable-agents-verifier.yml"
REUSABLE_CODEX_RUN = WORKFLOWS_DIR / "reusable-codex-run.yml"
NEEDS_HUMAN_COMMENT = Path("agents/codex-1447.md")
REFERENCE_PACK_FIXTURES = Path("tests/workflows/fixtures/reference_packs")


def _load_text(path: Path) -> str:
    assert path.exists(), f"Workflow {path.name} must exist"
    return path.read_text(encoding="utf-8")


def _load_workflow(path: Path) -> dict:
    return yaml.safe_load(_load_text(path))


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
    assert match is None, (
        f"{name} contains floating langchain install: " f"`{match.group(0).strip()}`"
    )


def _iter_steps(workflow: dict) -> list[dict]:
    steps: list[dict] = []
    for job in (workflow.get("jobs") or {}).values():
        job_steps = job.get("steps") or []
        if isinstance(job_steps, list):
            steps.extend(step for step in job_steps if isinstance(step, dict))
    return steps


def _find_step_by_name(workflow: dict, step_name: str) -> dict:
    for step in _iter_steps(workflow):
        if step.get("name") == step_name:
            return step
    raise AssertionError(f"Missing workflow step: {step_name}")


def _assert_pip_cache(workflow: dict, hash_path: str, name: str) -> None:
    expected_hash = f"hashFiles('{hash_path}')"
    expected_hash_alt = f'hashFiles("{hash_path}")'
    for step in _iter_steps(workflow):
        if step.get("uses") != "actions/cache@v5":
            continue
        with_block = step.get("with") or {}
        key = str(with_block.get("key", ""))
        if (expected_hash in key or expected_hash_alt in key) and "python-version" in key:
            return
    raise AssertionError(
        f"{name} must include actions/cache@v5 step with key using python-version and hashFiles('{hash_path}')."
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
) -> str:
    assemble_step = _find_step_by_name(workflow, "Assemble prompt")
    run_script = str(assemble_step.get("run", ""))
    base_prompt = tmp_path / "base_prompt.md"
    base_prompt.write_text(base_prompt_text, encoding="utf-8")
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
        "pip install -r tools/requirements-llm.txt",
        AUTO_PILOT.name,
    )
    _assert_no_floating_langchain(text, AUTO_PILOT.name)


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


def test_workflow_llm_needs_human_comment_documents_blocker() -> None:
    text = _load_text(NEEDS_HUMAN_COMMENT)
    required_phrases = [
        "Label: needs-human",
        ".github/workflows/agents-auto-pilot.yml",
        ".github/workflows/reusable-agents-verifier.yml",
        "actions/cache@v5",
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


def test_reusable_codex_workflow_has_reference_pack_validation_step() -> None:
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    step = _find_step_by_name(workflow, "Validate and materialize reference packs")
    run_script = str(step.get("run", ""))
    # Step must validate config with reference_packs.py
    assert "reference_packs.py" in run_script
    # Step must no-op when config file is absent
    assert "reference_packs.json" in run_script
    # Step must be positioned before Assemble prompt
    steps = _iter_steps(workflow)
    step_names = [s.get("name", "") for s in steps]
    ref_idx = step_names.index("Validate and materialize reference packs")
    prompt_idx = step_names.index("Assemble prompt")
    codex_idx = step_names.index("Run Codex")
    assert (
        ref_idx < prompt_idx < codex_idx
    ), "Reference pack validation must come before Assemble prompt and Run Codex"


def test_reusable_codex_reference_pack_step_handles_sha_refs() -> None:
    """The materialization script must detect full 40-char hex SHAs and use
    clone+fetch+checkout instead of --branch, and suppress stderr on clone
    commands to avoid leaking tokens."""
    workflow = _load_workflow(REUSABLE_CODEX_RUN)
    step = _find_step_by_name(workflow, "Validate and materialize reference packs")
    run_script = str(step.get("run", ""))
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
