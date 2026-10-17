import io
import json
import sys
import types
from pathlib import Path

import pytest
from tools import ci_failure_triage, llm_registry


def test_default_playbooks_are_distributed_with_valid_anchors():
    import yaml

    root = Path(__file__).resolve().parents[2]
    assert (root / "tools/ci_failure_triage.py").read_bytes() == (
        root / "templates/consumer-repo/tools/ci_failure_triage.py"
    ).read_bytes()
    manifest = yaml.safe_load((root / ".github/sync-manifest.yml").read_text())
    docs = {entry.get("target", entry["source"]): entry for entry in manifest["docs"]}
    for pattern in ci_failure_triage.DEFAULT_TRIAGE_PATTERNS:
        path, anchor = pattern.playbook_url.split("#", 1)
        assert path in docs, f"Undistributed playbook: {path}"
        assert (root / path).is_file()
        content = (root / path).read_text()
        assert f"## {anchor.replace('-', ' ').title()}" in content
        assert (root / "templates/consumer-repo" / path).read_text() == content


def test_extract_pytest_failures_parses_unique() -> None:
    log_text = "\n".join(
        [
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param] - ValueError",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    failures = ci_failure_triage.extract_pytest_failures(log_text)

    assert failures == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token",
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_prefers_dedicated_dispatch_token[param]",
    ]


def test_triage_report_includes_failed_tests() -> None:
    log_text = "\n".join(
        [
            "=================================== FAILURES ===================================",
            "FAILED tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token - AssertionError",
        ]
    )

    report = ci_failure_triage.triage_ci_failure(log_text)

    assert report.failed_tests == [
        "tests/workflows/test_keepalive_workflow.py::test_keepalive_requires_dispatch_token"
    ]
    assert "Pytest failures: 1" in report.summary


def test_llm_triage_does_not_fall_back_outside_slot_allowlist(monkeypatch) -> None:
    created: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(llm_registry, "configured_model_for_provider", lambda _provider: "")

    assert ci_failure_triage._get_llm_client() is None
    assert created == []


def test_llm_triage_falls_back_from_github_models_to_openai(monkeypatch) -> None:
    created: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        llm_registry,
        "configured_model_for_provider",
        lambda provider: "" if provider == "github-models" else "gpt-5-mini",
    )

    client_and_provider = ci_failure_triage._get_llm_client()

    assert client_and_provider is not None
    client, provider = client_and_provider
    assert provider == "openai"
    assert isinstance(client, FakeChatOpenAI)
    assert created == [{"model": "gpt-5-mini", "api_key": "openai-token", "temperature": 0.1}]


def test_llm_triage_does_not_use_empty_openai_token(monkeypatch) -> None:
    created: list[object] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")

    assert ci_failure_triage._get_llm_client() is None
    assert created == []


def test_triage_detects_patterns_deduplicates_paths_and_formats_reports() -> None:
    log_text = "\n".join(
        [
            "src/example.py:12: error: bad [arg-type]",
            "=================================== FAILURES ===================================",
            "FAILED tests/test_example.py::test_one - AssertionError",
            "coverage failure: required test coverage of 90% not reached",
            'File "tools/example.py", line 4, in <module>: ModuleNotFoundError: No module named example',
            "SyntaxError: unexpected EOF while parsing",
        ]
    )

    report = ci_failure_triage.triage_ci_failure(log_text, use_llm=False)

    assert [finding.error_type for finding in report.findings] == [
        "mypy",
        "pytest",
        "coverage",
        "import_error",
        "syntax_error",
    ]
    assert report.findings[0].relevant_files == ["src/example.py"]
    assert "src/example.py" in report.findings[0].suggested_fix
    assert report.findings[3].relevant_files == ["tools/example.py"]
    assert report.failed_tests == ["tests/test_example.py::test_one"]
    assert "Pytest failures: 1" in report.summary
    assert ci_failure_triage._report_to_dict(report)["findings"][0]["evidence"]
    text = ci_failure_triage._format_text_report(report)
    assert "Failing tests:" in text
    assert "playbook_url: docs/CI_FAILURE_PLAYBOOK.md#type-errors" in text


def test_triage_helpers_handle_unknown_and_malformed_llm_data(monkeypatch) -> None:
    assert ci_failure_triage._format_suggested_fix("fixed", []) == "fixed"
    assert ci_failure_triage._format_suggested_fix("fix {files}", []) == "fix the reported files"
    assert ci_failure_triage._build_summary([], ["tests/test_x.py::test_x"]) == (
        "Detected failing tests without a known failure pattern."
    )
    assert (
        ci_failure_triage._format_text_report(
            ci_failure_triage.TriageReport([], "nothing", ["tests/test_x.py::test_x"])
        )
        == "nothing\nFailing tests:\n- tests/test_x.py::test_x"
    )
    assert (
        ci_failure_triage._format_text_report(ci_failure_triage.TriageReport([], "nothing"))
        == "nothing"
    )
    assert ci_failure_triage.extract_pytest_failures("FAILED \nnot a failure") == []
    assert ci_failure_triage._extract_json_payload("no json") is None
    assert (
        ci_failure_triage._extract_json_payload('before {"findings": []} after')
        == '{"findings": []}'
    )
    assert ci_failure_triage._parse_llm_findings("{bad json}") == []
    assert ci_failure_triage._parse_llm_findings('{"findings": "wrong"}') == []
    assert ci_failure_triage._parse_llm_findings("no JSON here") == []
    assert ci_failure_triage._parse_llm_findings(
        json.dumps(
            {
                "findings": [
                    "not a finding",
                    {"error_type": "", "root_cause": "cause", "suggested_fix": "fix"},
                    {
                        "error_type": "custom",
                        "root_cause": "cause",
                        "suggested_fix": "fix",
                        "relevant_files": ["ok.py", 1, ""],
                        "playbook_url": " ",
                    },
                ]
            }
        )
    ) == [ci_failure_triage.TriageFinding("custom", "cause", "fix", ["ok.py"])]
    assert ci_failure_triage._bool_env(None) is False
    assert ci_failure_triage._bool_env(" YES ") is True
    assert ci_failure_triage._bool_env("no") is False

    base = ci_failure_triage.TriageReport(
        [ci_failure_triage.TriageFinding("pytest", "base", "fix", [])], "base"
    )
    monkeypatch.setattr(
        ci_failure_triage,
        "_run_llm_triage",
        lambda _log: [
            ci_failure_triage.TriageFinding("pytest", "duplicate", "fix", []),
            ci_failure_triage.TriageFinding("new", "cause", "fix", []),
        ],
    )
    enhanced = ci_failure_triage._maybe_enhance_with_llm(base, "log", True)
    assert [finding.error_type for finding in enhanced.findings] == ["pytest", "new"]
    monkeypatch.setattr(ci_failure_triage, "_run_llm_triage", lambda _log: [])
    assert ci_failure_triage._maybe_enhance_with_llm(base, "log", True) is base
    assert (
        ci_failure_triage._format_text_report(
            ci_failure_triage.TriageReport(
                [ci_failure_triage.TriageFinding("test", "cause", "fix", [])], "one"
            )
        )
        == "one\n- error_type: test\n  root_cause: cause\n  suggested_fix: fix"
    )


def test_llm_prompt_client_and_cli_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    prompt = ci_failure_triage._build_llm_prompt(" x " * 5000)
    assert "CI failure triage assistant" in prompt
    assert len(prompt.split("Log snippet:\n", 1)[1]) == 8000

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(llm_registry, "configured_model_for_provider", lambda _provider: "model")
    client_and_provider = ci_failure_triage._get_llm_client()
    assert client_and_provider is not None
    client, provider = client_and_provider
    assert provider == "github-models"
    assert client.kwargs["api_key"] == "github-token"
    monkeypatch.setattr(llm_registry, "configured_model_for_provider", lambda _provider: "")
    assert ci_failure_triage._get_llm_client() is None
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
    assert ci_failure_triage._get_llm_client() is None
    monkeypatch.setitem(
        sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
    )

    class RaisingClient:
        def invoke(self, _prompt: str) -> object:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(ci_failure_triage, "_get_llm_client", lambda: (RaisingClient(), "test"))
    assert ci_failure_triage._run_llm_triage("log") == []
    monkeypatch.setattr(ci_failure_triage, "_get_llm_client", lambda: None)
    assert ci_failure_triage._run_llm_triage("log") == []

    class RespondingClient:
        def invoke(self, _prompt: str) -> object:
            return types.SimpleNamespace(
                content=(
                    'prefix {"findings": [{"error_type": "llm", "root_cause": "cause", '
                    '"suggested_fix": "fix", "playbook_url": "docs/x"}]} suffix'
                )
            )

    monkeypatch.setattr(ci_failure_triage, "_get_llm_client", lambda: (RespondingClient(), "test"))
    findings = ci_failure_triage._run_llm_triage("log")
    assert findings == [ci_failure_triage.TriageFinding("llm", "cause", "fix", [], "docs/x")]
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert ci_failure_triage._read_log_text(None) == ""
    log_file = tmp_path / "failure.log"
    log_file.write_text("coverage failure", encoding="utf-8")
    assert ci_failure_triage._read_log_text(str(log_file)) == "coverage failure"
    with pytest.raises(SystemExit, match="Error reading log file"):
        ci_failure_triage._read_log_text(str(tmp_path / "missing.log"))

    monkeypatch.setattr(sys, "stdin", io.StringIO("coverage failure"))
    assert ci_failure_triage.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["findings"][0]["error_type"] == "coverage"
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert ci_failure_triage.main([]) == 0
    assert capsys.readouterr().out == "No known failure patterns detected.\n"
