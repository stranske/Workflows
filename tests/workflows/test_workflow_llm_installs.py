from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(".github/workflows")
AUTO_PILOT = WORKFLOWS_DIR / "agents-auto-pilot.yml"
VERIFIER = WORKFLOWS_DIR / "reusable-agents-verifier.yml"
NEEDS_HUMAN_COMMENT = Path("agents/codex-1447.md")


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


def test_agents_auto_pilot_llm_install_is_pinned() -> None:
    text = _load_text(AUTO_PILOT)
    _assert_pinned_install(
        text,
        "pip install -r tools/requirements-llm.txt",
        AUTO_PILOT.name,
    )
    _assert_no_floating_langchain(text, AUTO_PILOT.name)


def test_agents_auto_pilot_pip_cache_is_configured() -> None:
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
