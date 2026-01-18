from __future__ import annotations

import io
import re
import runpy
import sys
import types
from unittest.mock import patch

from scripts.langchain import task_decomposer


def test_decompose_task_fallback_adds_verification() -> None:
    result = task_decomposer.decompose_task("Update docs and add tests", use_llm=False)
    sub_tasks = result["sub_tasks"]
    assert len(sub_tasks) >= 2
    assert all("verify" in task.lower() for task in sub_tasks)


def test_normalize_subtasks_splits_multi_action() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["Update docs and add tests"])
    assert len(sub_tasks) == 2
    assert any("update docs" in task.lower() for task in sub_tasks)
    assert any("add tests" in task.lower() for task in sub_tasks)
    assert all("verify" in task.lower() for task in sub_tasks)
    assert any("docs updated" in task.lower() for task in sub_tasks)
    assert any("tests pass" in task.lower() for task in sub_tasks)


def test_normalize_subtasks_strips_dependency_clause() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["After merging PR #123, update docs"])
    assert len(sub_tasks) == 1
    assert "after merging" not in sub_tasks[0].lower()
    assert "update docs" in sub_tasks[0].lower()


def test_normalize_subtasks_rephrases_dependency_phrases() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(["Depends on backend merge"])
    assert len(sub_tasks) == 1
    assert sub_tasks[0].lower().startswith("document dependency for:")
    assert "depends on" not in sub_tasks[0].lower()
    assert "verify" in sub_tasks[0].lower()


def test_normalize_subtasks_scopes_large_tasks() -> None:
    sub_tasks = task_decomposer._normalize_subtasks(
        ["Implement end-to-end workflow for keepalive metrics collection"]
    )
    assert len(sub_tasks) == 3
    assert any(task.lower().startswith("define scope for:") for task in sub_tasks)
    assert any(task.lower().startswith("implement focused slice for:") for task in sub_tasks)
    assert any(task.lower().startswith("validate focused slice for:") for task in sub_tasks)
    assert all("verify" in task.lower() for task in sub_tasks)


def test_build_child_issues_skips_atomic_task() -> None:
    child_issues = task_decomposer.build_child_issues(["update docs"], parent_title="Parent Issue")
    assert child_issues == []


def test_build_child_issues_preserves_metadata() -> None:
    child_issues = task_decomposer.build_child_issues(
        ["update docs", "add tests"],
        parent_title="Parent Issue",
        parent_number=123,
        parent_url="https://github.com/example/repo/issues/123",
        labels=["agent:codex", "status:ready"],
        assignees=["octo-user"],
        milestone=7,
    )
    assert len(child_issues) == 2
    for child in child_issues:
        assert child["labels"] == ["agent:codex", "status:ready"]
        assert child["assignees"] == ["octo-user"]
        assert child["milestone"] == 7
        assert child["title"].startswith("Parent Issue:")
        assert "Parent issue: [#123](" in child["body"]
        assert "- [ ] " in child["body"]
    assert child_issues[0]["labels"] is not child_issues[1]["labels"]
    assert child_issues[0]["assignees"] is not child_issues[1]["assignees"]


def test_build_child_issues_from_parent_copies_metadata() -> None:
    parent_issue = {
        "title": "Parent Issue",
        "number": 456,
        "html_url": "https://github.com/example/repo/issues/456",
        "labels": [{"name": "agent:codex"}, {"name": "status:ready"}],
        "assignees": [{"login": "octo-user"}],
        "milestone": {"number": 9, "title": "Milestone 9"},
    }
    child_issues = task_decomposer.build_child_issues_from_parent(
        ["update docs", "add tests"],
        parent_issue=parent_issue,
    )
    assert len(child_issues) == 2
    for child in child_issues:
        assert child["labels"] == ["agent:codex", "status:ready"]
        assert child["assignees"] == ["octo-user"]
        assert child["milestone"] == 9
        assert child["title"].startswith("Parent Issue:")
        assert "Parent issue: [#456](" in child["body"]


def test_parent_child_linking_bidirectional() -> None:
    parent_issue = {
        "title": "Parent Issue",
        "number": 789,
        "html_url": "https://github.com/example/repo/issues/789",
    }
    child_payloads = task_decomposer.build_child_issues_from_parent(
        ["update docs", "add tests"],
        parent_issue=parent_issue,
    )
    assert child_payloads
    for child in child_payloads:
        assert "Parent issue: [#789](" in child["body"]

    created_children = []
    for idx, child in enumerate(child_payloads, start=1):
        created_children.append(
            {
                **child,
                "number": 900 + idx,
                "html_url": f"https://github.com/example/repo/issues/{900 + idx}",
            }
        )

    parent_body = "## Tasks\n- [ ] Parent task"
    updated = task_decomposer.build_parent_issue_update(parent_body, created_children)
    assert "## Child Issues" in updated
    assert "- [#901](" in updated
    assert "- [#902](" in updated
    assert "## Tasks" in updated


def test_decompose_task_empty_input() -> None:
    """decompose_task returns empty sub_tasks for empty input."""
    result = task_decomposer.decompose_task("")
    assert result["sub_tasks"] == []
    assert result["provider_used"] is None
    assert result["used_llm"] is False


def test_decompose_task_whitespace_only() -> None:
    """decompose_task returns empty sub_tasks for whitespace-only input."""
    result = task_decomposer.decompose_task("   \n\t  ")
    assert result["sub_tasks"] == []


def test_decompose_task_skips_atomic_task() -> None:
    """decompose_task returns empty sub_tasks for atomic tasks."""
    result = task_decomposer.decompose_task("Fix null check in parser", use_llm=False)
    assert result["sub_tasks"] == []


def test_split_task_parts_with_then() -> None:
    """_split_task_parts splits on ' then '."""
    parts = task_decomposer._split_task_parts("update config then run tests")
    assert len(parts) == 2
    assert "update config" in parts
    assert "run tests" in parts


def test_split_task_parts_with_semicolon() -> None:
    """_split_task_parts splits on semicolons."""
    parts = task_decomposer._split_task_parts("fix bug; write tests; deploy")
    assert len(parts) == 3


def test_split_task_parts_with_comma() -> None:
    """_split_task_parts splits on commas."""
    parts = task_decomposer._split_task_parts("lint, format, typecheck")
    assert len(parts) == 3


def test_split_task_parts_expands_parenthesized_lists() -> None:
    """_split_task_parts intelligently expands parenthesized lists.

    This prevents tasks like "Add stats (mean, p50, p90)" from becoming
    garbage fragments like "Add stats (mean", "p50", "p90)".
    Instead, it expands to clean individual tasks.
    """
    # Parenthesized list should be expanded intelligently
    parts = task_decomposer._split_task_parts("Add statistical aggregation (mean, p50, p90, p99)")
    assert len(parts) == 4
    assert parts[0] == "Add statistical aggregation for mean"
    assert parts[1] == "Add statistical aggregation for p50"
    assert parts[2] == "Add statistical aggregation for p90"
    assert parts[3] == "Add statistical aggregation for p99"

    # Function signatures (no commas) should stay intact
    parts = task_decomposer._split_task_parts("Create calculate_stats(data)")
    assert len(parts) == 1

    # Multiple parenthesized groups - expand intelligently
    parts = task_decomposer._split_task_parts("Add metrics (latency, throughput)")
    assert len(parts) == 2
    assert "latency" in parts[0]
    assert "throughput" in parts[1]

    # Single item in parens - keep intact (no expansion needed)
    parts = task_decomposer._split_task_parts("Create file (test.py)")
    assert len(parts) == 1


def test_split_task_parts_with_with_list() -> None:
    """_split_task_parts expands list items after 'with'."""
    parts = task_decomposer._split_task_parts(
        "Build user dashboard with auth, profile, settings, notifications, themes, export, import, admin"
    )
    assert len(parts) == 8
    assert all(part.startswith("Build user dashboard with") for part in parts)


def test_split_task_parts_with_spaced_slash() -> None:
    """_split_task_parts splits on spaced slashes ' / '."""
    parts = task_decomposer._split_task_parts("option A / option B")
    assert len(parts) == 2
    assert "option A" in parts
    assert "option B" in parts


def test_parse_subtasks_accepts_alpha_items() -> None:
    """_parse_subtasks accepts alpha-enumerated list items."""
    text = "a) First task\nb) Second task\nc) Third task"
    parsed = task_decomposer._parse_subtasks(text)
    assert parsed == ["First task", "Second task", "Third task"]


def test_split_task_parts_preserves_compound_words() -> None:
    """_split_task_parts does NOT split compound words with unspaced slashes."""
    # Compound words like "additions/removals" should NOT be split
    parts = task_decomposer._split_task_parts("config/settings")
    assert parts == ["config/settings"]

    parts = task_decomposer._split_task_parts("additions/removals")
    assert parts == ["additions/removals"]

    # Paths like "src/utils/helpers" should NOT be split
    parts = task_decomposer._split_task_parts("Update src/utils/helpers module")
    assert parts == ["Update src/utils/helpers module"]


def test_split_task_parts_single_task() -> None:
    """_split_task_parts returns single element for simple task."""
    parts = task_decomposer._split_task_parts("simple task")
    assert parts == ["simple task"]


def test_word_count() -> None:
    """_word_count counts alphanumeric words."""
    assert task_decomposer._word_count("hello world") == 2
    assert task_decomposer._word_count("it's a test") == 3
    assert task_decomposer._word_count("") == 0


def test_is_large_task_by_keywords() -> None:
    """_is_large_task detects large task keywords."""
    assert task_decomposer._is_large_task("full migration of database")
    assert task_decomposer._is_large_task("overall system redesign")
    assert task_decomposer._is_large_task("refactor entire codebase")
    assert task_decomposer._is_large_task("migrate to new api")
    assert task_decomposer._is_large_task("consolidate modules")
    assert task_decomposer._is_large_task("rollout new features")


def test_is_large_task_by_word_count() -> None:
    """_is_large_task detects tasks exceeding MAX_SUBTASK_WORDS."""
    long_task = "this is a very long task description that exceeds the maximum word limit"
    assert task_decomposer._is_large_task(long_task)


def test_is_large_task_small_task() -> None:
    """_is_large_task returns False for small tasks."""
    assert not task_decomposer._is_large_task("fix bug")
    assert not task_decomposer._is_large_task("add test")


def test_is_large_task_prefix_with_keyword() -> None:
    """_is_large_task handles prefixes with large keywords."""
    assert task_decomposer._is_large_task("implement full system")
    assert task_decomposer._is_large_task("define migration plan")


def test_infer_verification_patterns() -> None:
    """_infer_verification returns appropriate verification for various patterns."""
    assert task_decomposer._infer_verification("add tests for module") == "tests pass"
    assert task_decomposer._infer_verification("update documentation") == "docs updated"
    assert task_decomposer._infer_verification("run black formatter") == "formatter passes"
    assert task_decomposer._infer_verification("fix lint errors") == "lint passes"
    assert task_decomposer._infer_verification("run mypy typecheck") == "typecheck passes"
    assert task_decomposer._infer_verification("bump dependencies") == "dependencies updated"
    assert task_decomposer._infer_verification("update config file") == "config validated"
    assert task_decomposer._infer_verification("random task") is None


def test_ensure_verification_adds_verify() -> None:
    """_ensure_verification adds verification when missing."""
    result = task_decomposer._ensure_verification("add tests")
    assert "verify" in result.lower()
    assert "tests pass" in result.lower()


def test_ensure_verification_keeps_existing() -> None:
    """_ensure_verification keeps existing verify clause."""
    task = "update docs (verify: reviewed)"
    result = task_decomposer._ensure_verification(task)
    assert result == task


def test_contains_dependency_phrase() -> None:
    """_contains_dependency_phrase detects dependency patterns."""
    assert task_decomposer._contains_dependency_phrase("depends on PR merge")
    assert task_decomposer._contains_dependency_phrase("blocked by backend")
    assert task_decomposer._contains_dependency_phrase("waiting for review")
    assert task_decomposer._contains_dependency_phrase("post-merge cleanup")
    assert task_decomposer._contains_dependency_phrase("after merge, deploy")
    assert not task_decomposer._contains_dependency_phrase("simple task")


def test_rewrite_dependency_task() -> None:
    """_rewrite_dependency_task reformats dependency tasks."""
    result = task_decomposer._rewrite_dependency_task("depends on backend merge")
    assert result.startswith("Document dependency for:")
    assert "depends on" not in result.lower()
    assert "verify" in result.lower()


def test_rewrite_dependency_task_empty_cleaned() -> None:
    """_rewrite_dependency_task handles edge case where cleaned text is empty."""
    result = task_decomposer._rewrite_dependency_task("depends on")
    assert "dependency details" in result.lower()


def test_parse_subtasks_various_formats() -> None:
    """_parse_subtasks handles various list formats."""
    text = """
    - First task
    * Second task
    + Third task
    1. Fourth task
    2) Fifth task
    Plain line
    """
    tasks = task_decomposer._parse_subtasks(text)
    assert len(tasks) == 6
    assert "First task" in tasks
    assert "Plain line" in tasks


def test_parse_subtasks_empty_lines() -> None:
    """_parse_subtasks skips empty lines."""
    text = "\n\n- task\n\n"
    tasks = task_decomposer._parse_subtasks(text)
    assert tasks == ["task"]


def test_fallback_decompose_empty() -> None:
    """_fallback_decompose returns empty list for empty input."""
    result = task_decomposer._fallback_decompose("")
    assert result == []


def test_fallback_decompose_multi_part() -> None:
    """_fallback_decompose splits multi-part tasks."""
    result = task_decomposer._fallback_decompose("task A and task B")
    assert len(result) == 2


def test_fallback_decompose_single_task() -> None:
    """_fallback_decompose creates standard decomposition for single tasks."""
    result = task_decomposer._fallback_decompose("single task")
    assert len(result) == 3
    assert any("define approach" in t.lower() for t in result)
    assert any("implement" in t.lower() for t in result)
    assert any("validate" in t.lower() for t in result)


def test_expand_large_task() -> None:
    """_expand_large_task creates scoped sub-tasks."""
    result = task_decomposer._expand_large_task("big project")
    assert len(result) == 3
    assert any("define scope" in t.lower() for t in result)
    assert any("implement focused slice" in t.lower() for t in result)
    assert any("validate focused slice" in t.lower() for t in result)


def test_strip_dependency_clause() -> None:
    """_strip_dependency_clause removes leading dependency clauses."""
    assert task_decomposer._strip_dependency_clause("after merge, deploy") == "deploy"
    assert task_decomposer._strip_dependency_clause("once done, test") == "test"
    assert task_decomposer._strip_dependency_clause("simple task") == "simple task"


def test_normalize_subtasks_public_api() -> None:
    """normalize_subtasks is accessible as public API."""
    result = task_decomposer.normalize_subtasks(["update docs"])
    assert len(result) == 1
    assert "verify" in result[0].lower()


def test_load_prompt_fallback() -> None:
    """_load_prompt returns default template when file doesn't exist."""
    prompt = task_decomposer._load_prompt()
    assert "Decompose into smaller" in prompt


def test_load_prompt_existing_file(monkeypatch, tmp_path) -> None:
    """_load_prompt reads content from prompt file when present."""
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Use this prompt.", encoding="utf-8")
    monkeypatch.setattr(task_decomposer, "PROMPT_PATH", prompt_path)
    assert task_decomposer._load_prompt() == "Use this prompt."


def test_load_prompt_missing_file(monkeypatch, tmp_path) -> None:
    """_load_prompt falls back when prompt file is missing."""
    missing_path = tmp_path / "missing.md"
    monkeypatch.setattr(task_decomposer, "PROMPT_PATH", missing_path)
    prompt = task_decomposer._load_prompt()
    assert prompt == task_decomposer.TASK_DECOMPOSITION_PROMPT


def test_load_prompt_missing_file_falls_back(monkeypatch, tmp_path) -> None:
    """_load_prompt returns default prompt when file is absent."""
    missing_path = tmp_path / "absent.md"
    monkeypatch.setattr(task_decomposer, "PROMPT_PATH", missing_path)
    assert not missing_path.exists()
    prompt = task_decomposer._load_prompt()
    assert prompt == task_decomposer.TASK_DECOMPOSITION_PROMPT


def test_load_prompt_default_template(monkeypatch, tmp_path) -> None:
    """_load_prompt uses default template when prompt file is absent."""
    missing_path = tmp_path / "nope.md"
    monkeypatch.setattr(task_decomposer, "PROMPT_PATH", missing_path)
    assert task_decomposer._load_prompt() == task_decomposer.TASK_DECOMPOSITION_PROMPT


def _install_fake_langchain_openai(monkeypatch):
    fake_module = types.ModuleType("langchain_openai")

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)
    return FakeChatOpenAI


def test_get_llm_client_missing_dependency(monkeypatch) -> None:
    """_get_llm_client returns None when langchain_openai is unavailable."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delitem(sys.modules, "langchain_openai", raising=False)

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "langchain_openai":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    assert task_decomposer._get_llm_client() is None


def test_get_llm_client_no_tokens(monkeypatch) -> None:
    """_get_llm_client returns None when no API tokens are set."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert task_decomposer._get_llm_client() is None


def test_get_llm_client_with_github_token(monkeypatch) -> None:
    """_get_llm_client uses GitHub Models when GITHUB_TOKEN is set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client_info = task_decomposer._get_llm_client()
    assert client_info is not None
    client, provider = client_info
    assert provider == "github-models"
    assert isinstance(client, FakeChatOpenAI)
    assert client.kwargs["api_key"] == "token"


def test_get_llm_client_github_token_defaults(monkeypatch) -> None:
    """_get_llm_client passes model and base_url for GitHub Models."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client_info = task_decomposer._get_llm_client()
    assert client_info is not None
    client, provider = client_info
    assert provider == "github-models"
    assert isinstance(client, FakeChatOpenAI)
    from tools import llm_provider

    assert client.kwargs["model"] == llm_provider.DEFAULT_MODEL
    assert client.kwargs["base_url"] == llm_provider.GITHUB_MODELS_BASE_URL


def test_get_llm_client_with_openai_token(monkeypatch) -> None:
    """_get_llm_client uses OpenAI when only OPENAI_API_KEY is set."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    client_info = task_decomposer._get_llm_client()
    assert client_info is not None
    client, provider = client_info
    assert provider == "openai"
    assert isinstance(client, FakeChatOpenAI)
    assert client.kwargs["api_key"] == "openai-token"
    assert client.kwargs["temperature"] == 0.1


def test_get_llm_client_prefers_github_token(monkeypatch) -> None:
    """_get_llm_client prefers GitHub Models when both tokens exist."""
    FakeChatOpenAI = _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    client_info = task_decomposer._get_llm_client()
    assert client_info is not None
    client, provider = client_info
    assert provider == "github-models"
    assert isinstance(client, FakeChatOpenAI)


def test_decompose_task_llm_path(monkeypatch) -> None:
    """decompose_task uses LLM output when available."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_prompts = types.ModuleType("langchain_core.prompts")

    class FakeChain:
        def invoke(self, values):
            return types.SimpleNamespace(content="- Add tests\n- Update docs")

    class FakeChatPromptTemplate:
        @classmethod
        def from_template(cls, template):
            return cls()

        def __or__(self, client):
            return FakeChain()

    fake_prompts.ChatPromptTemplate = FakeChatPromptTemplate
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)

    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is True
    assert result["provider_used"] == "github-models"
    assert any("add tests" in task.lower() for task in result["sub_tasks"])


def test_decompose_task_llm_prompt_used(monkeypatch, tmp_path) -> None:
    """decompose_task uses prompt file content for LLM requests."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Prompt for {large_task}", encoding="utf-8")
    monkeypatch.setattr(task_decomposer, "PROMPT_PATH", prompt_path)

    fake_prompts = types.ModuleType("langchain_core.prompts")
    captured = {}

    class FakeChain:
        def invoke(self, values):
            return types.SimpleNamespace(content="- Add tests")

    class FakeChatPromptTemplate:
        @classmethod
        def from_template(cls, template):
            captured["template"] = template
            return cls()

        def __or__(self, client):
            return FakeChain()

    fake_prompts.ChatPromptTemplate = FakeChatPromptTemplate
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)

    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is True
    assert captured["template"] == "Prompt for {large_task}"


def test_decompose_task_llm_response_without_content(monkeypatch) -> None:
    """decompose_task handles LLM responses without a content attribute."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_prompts = types.ModuleType("langchain_core.prompts")

    class FakeChain:
        def invoke(self, values):
            return "- Update docs\n- Add tests"

    class FakeChatPromptTemplate:
        @classmethod
        def from_template(cls, template):
            return cls()

        def __or__(self, client):
            return FakeChain()

    fake_prompts.ChatPromptTemplate = FakeChatPromptTemplate
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)

    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is True
    assert result["provider_used"] == "github-models"
    assert any("update docs" in task.lower() for task in result["sub_tasks"])


def test_decompose_task_llm_import_error(monkeypatch) -> None:
    """decompose_task falls back when langchain_core is unavailable."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delitem(sys.modules, "langchain_core.prompts", raising=False)

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "langchain_core.prompts":
            raise ImportError("missing")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is False
    assert result["provider_used"] is None


def test_decompose_task_llm_empty_result(monkeypatch) -> None:
    """decompose_task falls back when LLM returns no subtasks."""
    _install_fake_langchain_openai(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_prompts = types.ModuleType("langchain_core.prompts")

    class FakeChain:
        def invoke(self, values):
            return types.SimpleNamespace(content=" ")

    class FakeChatPromptTemplate:
        @classmethod
        def from_template(cls, template):
            return cls()

        def __or__(self, client):
            return FakeChain()

    fake_prompts.ChatPromptTemplate = FakeChatPromptTemplate
    monkeypatch.setitem(sys.modules, "langchain_core.prompts", fake_prompts)

    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is False
    assert result["provider_used"] is None


def test_decompose_task_no_llm_client(monkeypatch) -> None:
    """decompose_task falls back when no LLM client is available."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delitem(sys.modules, "langchain_openai", raising=False)
    result = task_decomposer.decompose_task("full migration of database", use_llm=True)
    assert result["used_llm"] is False
    assert result["provider_used"] is None


def test_main_json_output(monkeypatch) -> None:
    """main outputs JSON when --json flag is provided."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["task_decomposer.py", "--task", "Update docs and add tests", "--json", "--no-llm"],
    )
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        task_decomposer.main()
    output = captured.getvalue()
    assert '"sub_tasks"' in output
    assert '"used_llm": false' in output


def test_main_plain_output(monkeypatch) -> None:
    """main outputs plain text without --json flag."""
    monkeypatch.setattr(
        sys, "argv", ["task_decomposer.py", "--task", "Update docs and add tests", "--no-llm"]
    )
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        task_decomposer.main()
    output = captured.getvalue()
    assert output.startswith("-")
    assert "verify" in output.lower()


def test_main_empty_task(monkeypatch) -> None:
    """main handles empty task gracefully."""
    monkeypatch.setattr(sys, "argv", ["task_decomposer.py", "--json", "--no-llm"])
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        task_decomposer.main()
    output = captured.getvalue()
    assert '"sub_tasks": []' in output


def test_parse_subtasks_empty_list_item(monkeypatch) -> None:
    """_parse_subtasks skips list items with no content."""
    monkeypatch.setattr(task_decomposer, "LIST_ITEM_REGEX", re.compile(r"^(?P<empty>)"))
    tasks = task_decomposer._parse_subtasks("real task")
    assert tasks == []


def test_parse_subtasks_blank_bullet(monkeypatch) -> None:
    """_parse_subtasks skips bullets with empty content."""
    regex = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s*(.*)$")
    monkeypatch.setattr(task_decomposer, "LIST_ITEM_REGEX", regex)
    tasks = task_decomposer._parse_subtasks("-")
    assert tasks == []


def test_parse_subtasks_blank_bullet_default_regex() -> None:
    """_parse_subtasks keeps blank bullets when default regex doesn't match."""
    tasks = task_decomposer._parse_subtasks("- ")
    assert tasks == ["-"]


def test_parse_subtasks_empty_item_match(monkeypatch) -> None:
    """_parse_subtasks skips empty items when regex matches."""
    regex = re.compile(r"^\s*-\s*(.*)$")
    monkeypatch.setattr(task_decomposer, "LIST_ITEM_REGEX", regex)
    tasks = task_decomposer._parse_subtasks("-")
    assert tasks == []


def test_normalize_subtasks_skips_empty_entries() -> None:
    """_normalize_subtasks skips empty sub-task entries."""
    result = task_decomposer._normalize_subtasks([" ", "update docs"])
    assert len(result) == 1
    assert "update docs" in result[0].lower()


def test_normalize_subtasks_empty_after_strip(monkeypatch) -> None:
    """_normalize_subtasks skips parts that strip to empty."""
    call_state = {"count": 0}

    def fake_strip(task: str) -> str:
        call_state["count"] += 1
        if call_state["count"] == 1:
            return task
        return ""

    monkeypatch.setattr(task_decomposer, "_strip_dependency_clause", fake_strip)
    result = task_decomposer._normalize_subtasks(["non-empty"])
    assert result == []


def test_normalize_subtasks_skips_empty_part(monkeypatch) -> None:
    """_normalize_subtasks skips empty parts from splitter."""
    monkeypatch.setattr(task_decomposer, "_split_task_parts", lambda _: [""])
    result = task_decomposer._normalize_subtasks(["after merge, deploy"])
    assert result == []


def test_normalize_subtasks_skips_empty_cleaned(monkeypatch) -> None:
    """_normalize_subtasks skips parts that strip to empty strings."""

    def fake_strip(value: str) -> str:
        if value == "keep":
            return value
        return ""

    monkeypatch.setattr(task_decomposer, "_strip_dependency_clause", fake_strip)
    monkeypatch.setattr(task_decomposer, "_split_task_parts", lambda _: ["", "keep"])
    result = task_decomposer._normalize_subtasks(["keep"])
    assert len(result) == 1
    assert "keep" in result[0].lower()


def test_main_module_invocation(monkeypatch) -> None:
    """__main__ execution runs the CLI entrypoint."""
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setattr(
        sys, "argv", ["task_decomposer.py", "--task", "Update docs and add tests", "--no-llm"]
    )
    captured = io.StringIO()
    with patch("sys.stdout", captured):
        runpy.run_path(task_decomposer.__file__, run_name="__main__")
    output = captured.getvalue()
    assert output.startswith("-")
