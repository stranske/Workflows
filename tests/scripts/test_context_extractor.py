from __future__ import annotations

import argparse
import json
import sys
import types

from scripts.langchain import context_extractor


def test_extract_context_fallback_collects_entries() -> None:
    issue_body = """## Scope
We must keep the API stable.
Constraint: avoid workflow edits.

## Tasks
- [ ] update docs

Related: #123 and org/repo#45.
See https://example.com/spec.

Blocked by infra rollout.
"""
    comments = ["Depends on PR #99 for the API change."]
    result = context_extractor.extract_context(issue_body, comments=comments, use_llm=False)
    context = result["context_section"]

    assert "## Context for Agent" in context
    assert "### Design Decisions & Constraints" in context
    assert "We must keep the API stable." in context
    assert "Constraint: avoid workflow edits." in context
    assert "### Related Issues/PRs" in context
    assert "#123" in context
    assert "org/repo#45" in context
    assert "#99" in context
    assert "### References" in context
    assert "https://example.com/spec" in context
    assert "### Blockers & Dependencies" in context
    assert "Blocked by infra rollout." in context
    assert "update docs" not in context


def test_extract_context_fallback_returns_empty_when_no_context() -> None:
    issue_body = """## Tasks
- [ ] implement feature
"""
    result = context_extractor.extract_context(issue_body, use_llm=False)
    assert result["context_section"] == ""


def test_fallback_helpers_cover_fences_dedup_and_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "250")
    monkeypatch.setenv("ISSUE_PR_CONTEXT_WORKFLOW", "custom")
    assert context_extractor._context_token_budget() == 250
    assert context_extractor._context_workflow("default") == "custom"
    assert context_extractor._strip_code_fences(["keep", "```py", "drop", "```", "also keep"]) == [
        "keep",
        "also keep",
    ]
    assert context_extractor._normalize_line("- useful note") == "useful note"
    assert context_extractor._normalize_line("- [x] task") == ""
    assert context_extractor._unique(["One", "one", "", "Two"]) == ["One", "Two"]
    assert context_extractor._extract_references("https://a.example/x).") == ["https://a.example/x"]
    assert context_extractor._is_github_models_auth_error(Exception("401 Models denied"))
    assert not context_extractor._is_github_models_auth_error(Exception("403 models denied"))

    prompt = tmp_path / "prompt.md"
    prompt.write_text("prompt", encoding="utf-8")
    monkeypatch.setattr(context_extractor, "PROMPT_PATH", prompt)
    assert context_extractor._load_prompt() == "prompt"
    assert (
        context_extractor._load_input(argparse.Namespace(input_file=None, input_text="inline"))
        == "inline"
    )
    comments = tmp_path / "comments.json"
    comments.write_text(json.dumps(["one"]), encoding="utf-8")
    assert context_extractor._load_comments(
        argparse.Namespace(comments_file=str(comments), comments_text=None)
    ) == ["one"]


def test_extract_context_uses_llm_response_and_falls_back_after_missing_dependency(
    monkeypatch,
) -> None:
    class Response:
        content = "LLM context"

    class Trace:
        def as_dict(self):
            return {"trace_id": "trace"}

    class Template:
        def __or__(self, client):
            return client

    monkeypatch.setattr(context_extractor, "_capped_issue_body", lambda text, _: text)
    monkeypatch.setattr(context_extractor, "_get_llm_client", lambda **_: (object(), "openai"))
    monkeypatch.setattr(context_extractor, "_load_prompt", lambda: "prompt")
    monkeypatch.setattr(context_extractor, "TraceInfo", Trace)
    monkeypatch.setattr(
        context_extractor, "invoke_with_trace", lambda *_args, **_kw: (Response(), Trace())
    )
    prompts = types.ModuleType("langchain_core.prompts")
    prompts.ChatPromptTemplate = type(
        "ChatPromptTemplate", (), {"from_template": staticmethod(lambda _: Template())}
    )
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", prompts)
    assert context_extractor.extract_context("body")["context_section"] == "LLM context"


def test_context_cli_cap_and_github_models_auth_fallback(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    class Options:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(context_extractor, "ContextOptions", Options)
    monkeypatch.setattr(
        context_extractor,
        "build_issue_context",
        lambda issue, options: {"formatted_body": issue["body"] + " capped"},
    )
    monkeypatch.setenv("ISSUE_PR_CONTEXT_TOKEN_BUDGET", "invalid")
    assert context_extractor._capped_issue_body("body", "workflow") == "body capped"
    assert captured["token_budget"] == 4000

    class Response:
        content = "fallback LLM context"

    class Trace:
        def as_dict(self):
            return {}

    class Template:
        def __or__(self, client):
            return client

    prompts = types.ModuleType("langchain_core.prompts")
    prompts.ChatPromptTemplate = type(
        "ChatPromptTemplate", (), {"from_template": staticmethod(lambda _: Template())}
    )
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", prompts)
    clients = [(object(), "github-models"), (object(), "openai")]
    monkeypatch.setattr(context_extractor, "_get_llm_client", lambda **_: clients.pop(0))
    monkeypatch.setattr(context_extractor, "_load_prompt", lambda: "prompt")
    monkeypatch.setattr(context_extractor, "TraceInfo", Trace)
    calls = {"count": 0}

    def invoke(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("401 models denied")
        return Response(), Trace()

    monkeypatch.setattr(context_extractor, "invoke_with_trace", invoke)
    assert context_extractor.extract_context("body")["provider_used"] == "openai"

    input_file = tmp_path / "issue.md"
    input_file.write_text("Constraint: preserve CLI output", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["context", "--input-file", str(input_file), "--no-llm", "--json"]
    )
    context_extractor.main()
    assert json.loads(capsys.readouterr().out)["used_llm"] is False
