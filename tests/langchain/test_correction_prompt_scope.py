"""Inert tests at the optimizer's actual final prompt invocation boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda
from scripts.langchain import issue_optimizer as optimizer
from scripts.langchain.issue_pr_context import render_correction_context

BODY = """## Why
Keep this entire source issue, including its outer requirements.
## Tasks
- [ ] Preserve OUTER_REQUIREMENT_73.
## Acceptance Criteria
- [ ] Preserve OUTER_ACCEPTANCE_91.
<details><summary>Original issue</summary>
INNER_BODY_MUST_NOT_REPLACE_OUTER
</details>
"""


def context(kind):
    request = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/verifier_correction/integration-request.json"
        ).read_text()
    )
    required_tests = copy.deepcopy(request["required_tests"])
    required_tests.append(
        {
            "kind": "existing_selector",
            "id": "existing-31",
            "finding_id": request["finding"]["id"],
            "source_ref": "b" * 40,
            "path": "tests/test_existing.py",
            "selector": "tests/test_existing.py::test_exact_31",
            "file_sha256": "c" * 64,
        }
    )
    return {
        "schema": "closer-correction-coding-context/v1",
        "request_sha256": "a" * 64,
        "finding_text": "Exact finding: braces {remain data}, Unicode \u03bb and SOURCE_FINDING_45.",
        "incumbent": (
            {"kind": "no_incumbent"}
            if kind == "no_incumbent"
            else {
                "kind": "existing",
                "issue": {"number": 9, "node_id": "I_9"},
                "owner": "inert-owner",
            }
        ),
        "required_tests": required_tests,
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv("CORRECTION_CONTEXT_FILE", raising=False)
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "100000")
    # Prevent optional tokenizer metadata retrieval. The real existing fallback
    # estimate remains active; no provider/client SDK is constructed.
    monkeypatch.setitem(__import__("sys").modules, "tiktoken", None)
    monkeypatch.setattr(optimizer, "check_prompt_injection", lambda _: {"blocked": False})


def invoke(operation, *, correction_context=None, body=BODY):
    if operation == "analyze":
        return optimizer.analyze_issue(body, correction_context=correction_context)
    return optimizer.apply_suggestions(
        body,
        {"objective_criteria": [], "notes": "Preserve SUGGESTION_29"},
        correction_context=correction_context,
    )


def install_inert_client(monkeypatch, *, fail=False):
    captured = {"payloads": [], "rendered": [], "clients": []}

    def model(prompt):
        captured["rendered"].append(prompt.to_string())
        if fail:
            raise RuntimeError("inert provider failure")
        return SimpleNamespace(
            content="## Why\nInert\n## Tasks\n- [ ] Inert\n## Acceptance Criteria\n- [ ] Inert"
        )

    def client(**kwargs):
        captured["clients"].append(kwargs)
        return RunnableLambda(model), "inert"

    original = optimizer._invoke_llm_with_trace

    def traced(chain, inputs, **kwargs):
        captured["payloads"].append(copy.deepcopy(inputs))
        return original(chain, inputs, **kwargs)

    monkeypatch.setattr(optimizer, "_get_llm_client", client)
    monkeypatch.setattr(optimizer, "_invoke_llm_with_trace", traced)
    monkeypatch.setattr(
        optimizer, "_process_llm_response", lambda *a, **kw: ("inert analysis", None)
    )
    monkeypatch.setattr(optimizer, "_formatted_output_valid", lambda _: True)
    return captured


@pytest.mark.parametrize("operation", ["analyze", "apply"])
@pytest.mark.parametrize("kind", ["existing", "no_incumbent"])
def test_actual_payload_and_rendered_template_preserve_entire_scope(monkeypatch, operation, kind):
    scope = context(kind)
    captured = install_inert_client(monkeypatch)

    # Any regression into either destructive legacy fitter fails directly.
    def forbidden(*args, **kwargs):
        pytest.fail("correction scope entered legacy original-body reset/truncation")

    monkeypatch.setattr(optimizer, "_reset_oversized_body", forbidden)
    monkeypatch.setattr(optimizer, "_capped_issue_body", forbidden)
    result = invoke(operation, correction_context=scope)
    key = "issue_body" if operation == "analyze" else "original_body"
    expected = BODY + render_correction_context(scope)
    assert captured["payloads"][0][key] == expected
    template = (
        optimizer._load_prompt() if operation == "analyze" else optimizer._load_apply_prompt()
    )
    assert captured["rendered"] == ["Human: " + template.format(**captured["payloads"][0])]
    assert expected in captured["rendered"][0]
    for test in scope["required_tests"]:
        assert (test.get("selector") or test["specification"]) in captured["rendered"][0]
    if operation == "apply":
        assert result["formatted_body"] == BODY


@pytest.mark.parametrize("operation", ["analyze", "apply"])
def test_final_template_overflow_holds_before_client_creation(monkeypatch, operation):
    captured = install_inert_client(monkeypatch)
    scope = context("no_incumbent")
    # Raw body plus scope fits, but the actual final instruction template does not.
    from scripts.langchain.issue_pr_context import estimate_tokens

    size = estimate_tokens(BODY + render_correction_context(scope))
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", str(size + 1))
    with pytest.raises(ValueError, match="correction_scope_over_budget"):
        invoke(operation, correction_context=scope)
    assert captured == {"payloads": [], "rendered": [], "clients": []}


@pytest.mark.parametrize("operation", ["analyze", "apply"])
def test_client_failure_does_not_reset_or_replace_original_scope(monkeypatch, operation):
    captured = install_inert_client(monkeypatch, fail=True)
    result = invoke(operation, correction_context=context("existing"))
    key = "issue_body" if operation == "analyze" else "original_body"
    assert captured["payloads"][0][key].startswith(BODY)
    if operation == "apply":
        assert result["formatted_body"] == BODY


@pytest.mark.parametrize("operation", ["analyze", "apply"])
def test_absent_overlay_preserves_legacy_payload_pipeline(monkeypatch, operation):
    captured = install_inert_client(monkeypatch)
    seen = []
    monkeypatch.setattr(
        optimizer,
        "_reset_oversized_body",
        lambda body, workflow: seen.append(("reset", body)) or "LEGACY_RESET",
    )
    monkeypatch.setattr(
        optimizer,
        "_capped_issue_body",
        lambda body, workflow: seen.append(("cap", body)) or "LEGACY_CAPPED",
    )
    invoke(operation)
    key = "issue_body" if operation == "analyze" else "original_body"
    assert seen == [("reset", BODY), ("cap", "LEGACY_RESET")]
    assert captured["payloads"][0][key] == "LEGACY_CAPPED"
    assert "Admitted correction scope" not in captured["rendered"][0]


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema": "caller-truth/v1"},
        {"finding_text": ""},
        {"request_sha256": "invalid"},
        {"required_tests": []},
        {"required_tests": ["freeform command"]},
        {"required_tests": [{"kind": "shell_command", "command": "never execute"}]},
    ],
)
@pytest.mark.parametrize("operation", ["analyze", "apply"])
def test_invalid_renderer_schema_holds_before_any_client(monkeypatch, operation, mutation):
    captured = install_inert_client(monkeypatch)
    scope = context("no_incumbent") | mutation
    with pytest.raises(ValueError, match="correction_scope_invalid"):
        invoke(operation, correction_context=scope)
    assert captured == {"payloads": [], "rendered": [], "clients": []}


@pytest.mark.parametrize("operation", ["analyze", "apply"])
def test_token_limit_retry_keeps_identical_complete_correction_payload(monkeypatch, operation):
    from tools import llm_provider

    captured = install_inert_client(monkeypatch)
    clients = []

    def factory(**kwargs):
        clients.append(kwargs)

        def model(prompt):
            captured["rendered"].append(prompt.to_string())
            if not kwargs.get("force_openai"):
                raise RuntimeError("inert token limit")
            return SimpleNamespace(
                content="## Why\nInert\n## Tasks\n- [ ] Inert\n## Acceptance Criteria\n- [ ] Inert"
            )

        return RunnableLambda(model), "openai" if kwargs else "github-models"

    monkeypatch.setattr(optimizer, "_get_llm_client", factory)
    monkeypatch.setattr(llm_provider, "_is_token_limit_error", lambda _: True)
    result = invoke(operation, correction_context=context("existing"))
    assert clients == [{}, {"force_openai": True}]
    assert len(captured["payloads"]) == 2
    assert captured["payloads"][0] == captured["payloads"][1]
    assert captured["rendered"][0] == captured["rendered"][1]
    if operation == "apply":
        assert result["formatted_body"] == BODY


def runner_fixture(tmp_path):
    import json

    from scripts.runner_lib import core

    instruction = tmp_path / ".github/codex/AGENT_INSTRUCTIONS.md"
    instruction.parent.mkdir(parents=True)
    instruction.write_text("PROVIDER_INSTRUCTIONS_63\n", encoding="utf-8")
    (tmp_path / "base.md").write_text("BASE_TASK_24\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("REPOSITORY_GUIDANCE_46\n", encoding="utf-8")
    ordinary = (
        "PROVIDER_INSTRUCTIONS_63\n---\n\n## Task Prompt\nBASE_TASK_24"
        "\n\n## Run context\nINCUMBENT_APPENDIX_52\n\n## Repository Guidance\nREPOSITORY_GUIDANCE_46\n"
    )
    scope = context("existing") | {"original_issue_body": BODY}
    scope_file = tmp_path / "correction.json"
    scope_file.write_text(json.dumps(scope), encoding="utf-8")
    settings = {
        "workspace": str(tmp_path),
        "base_prompt_file": "base.md",
        "appendix": "INCUMBENT_APPENDIX_52",
        "output_file": "final-prompt.md",
        "correction_context_file": str(scope_file),
        "correction_token_budget": 100000,
    }
    return core, settings, scope, scope_file, ordinary


@pytest.mark.parametrize("kind", ["existing", "no_incumbent"])
def test_final_runner_prompt_and_written_provider_payload_retain_every_scope(tmp_path, kind):
    import json

    core, settings, scope, scope_file, ordinary = runner_fixture(tmp_path)
    scope["incumbent"] = context(kind)["incumbent"]
    scope_file.write_text(json.dumps(scope), encoding="utf-8")
    prompt = core.assemble_prompt(None, settings, "codex")
    expected = (
        ordinary
        + "\n## Complete original issue scope\n"
        + BODY
        + render_correction_context(scope)
        + "\n"
    )
    assert prompt.text == expected
    assert prompt.file == "final-prompt.md"
    assert (tmp_path / prompt.file).read_text(encoding="utf-8") == expected
    assert prompt.provider == "codex"
    for test in scope["required_tests"]:
        assert (test.get("selector") or test["specification"]) in prompt.text


def test_final_runner_absent_overlay_output_is_byte_compatible(tmp_path):
    core, settings, _, _, ordinary = runner_fixture(tmp_path)
    del settings["correction_context_file"]
    del settings["correction_token_budget"]
    prompt = core.assemble_prompt(None, settings, "codex")
    assert prompt.text == ordinary
    assert (tmp_path / prompt.file).read_bytes() == ordinary.encode()


@pytest.mark.parametrize(
    "failure",
    [
        "missing_file",
        "unconfigured",
        "zero",
        "nondigit",
        "overflow",
        "missing_original",
        "empty_original",
        "invalid_schema",
    ],
)
def test_final_runner_holds_leave_existing_prompt_file_untouched(tmp_path, failure):
    import json

    core, settings, scope, scope_file, _ = runner_fixture(tmp_path)
    output = tmp_path / settings["output_file"]
    output.write_text("PREEXISTING_PROMPT_MUST_SURVIVE", encoding="utf-8")
    if failure == "missing_file":
        scope_file.unlink()
    elif failure in {"unconfigured", "zero", "nondigit", "overflow"}:
        settings["correction_token_budget"] = {
            "unconfigured": None,
            "zero": 0,
            "nondigit": "not a number",
            "overflow": 1,
        }[failure]
    else:
        if failure == "missing_original":
            del scope["original_issue_body"]
        elif failure == "empty_original":
            scope["original_issue_body"] = " \n"
        else:
            scope["schema"] = "untrusted-shape"
        scope_file.write_text(json.dumps(scope), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        core.assemble_prompt(None, settings, "codex")
    assert output.read_text(encoding="utf-8") == "PREEXISTING_PROMPT_MUST_SURVIVE"
    output.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        core.assemble_prompt(None, settings, "codex")
    assert not output.exists()


def test_runner_assemble_cli_reads_exact_selected_context_and_budget(tmp_path, monkeypatch, capsys):
    core, settings, scope, scope_file, ordinary = runner_fixture(tmp_path)
    monkeypatch.setenv("CORRECTION_CONTEXT_FILE", str(scope_file))
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "100000")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    args = SimpleNamespace(
        workspace=str(tmp_path),
        base_prompt="base.md",
        appendix="INCUMBENT_APPENDIX_52",
        mode="",
        pr_number=9,
        output=settings["output_file"],
        task_appendix_file=None,
        materialize_reference_packs=False,
        materialize_orchestrator_skill=False,
        orchestrator_skill_pack=None,
        orchestrator_skill_enabled=None,
        reference_pack_name=None,
        provider="codex",
    )
    assert core._cmd_assemble(args) == 0
    written = (tmp_path / settings["output_file"]).read_text(encoding="utf-8")
    assert (
        written
        == ordinary
        + "\n## Complete original issue scope\n"
        + BODY
        + render_correction_context(scope)
        + "\n"
    )
    assert '"file": "final-prompt.md"' in capsys.readouterr().out
    (tmp_path / settings["output_file"]).unlink()
    monkeypatch.delenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET")
    with pytest.raises(ValueError, match="correction_budget_unconfigured"):
        core._cmd_assemble(args)
    assert not (tmp_path / settings["output_file"]).exists()


def test_isolated_trusted_runner_bootstrap_ignores_poisoned_consumer_python(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    _, settings, scope, _, ordinary = runner_fixture(tmp_path)
    poison = tmp_path / "scripts/runner_lib"
    poison.mkdir(parents=True)
    (tmp_path / "scripts/__init__.py").write_text("raise RuntimeError('POISON_PACKAGE_EXECUTED')\n")
    (poison / "__main__.py").write_text("raise RuntimeError('POISON_RUNNER_EXECUTED')\n")
    (tmp_path / "ast.py").write_text("raise RuntimeError('POISON_AST_EXECUTED')\n")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    env = os.environ.copy()
    env.update(
        {
            "CORRECTION_CONTEXT_FILE": settings["correction_context_file"],
            "ISSUE_PR_CONTEXT_TOKEN_BUDGET": "100000",
        }
    )
    env.pop("GITHUB_OUTPUT", None)
    env.pop("ORCHESTRATOR_SKILL_SUMMARY_PATH", None)
    trusted_root = Path(__file__).resolve().parents[2]
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('scripts.runner_lib',run_name='__main__')"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            bootstrap,
            str(trusted_root),
            "assemble-prompt",
            "--provider",
            "codex",
            "--workspace",
            str(tmp_path),
            "--base-prompt",
            "base.md",
            "--appendix",
            "INCUMBENT_APPENDIX_52",
            "--output",
            "final-prompt.md",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "POISON_" not in result.stdout + result.stderr
    assert (tmp_path / "final-prompt.md").read_text() == (
        ordinary
        + "\n## Complete original issue scope\n"
        + BODY
        + render_correction_context(scope)
        + "\n"
    )
