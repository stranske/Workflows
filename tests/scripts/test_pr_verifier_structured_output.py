from __future__ import annotations

import json
from unittest import mock

import pytest

from scripts.langchain import pr_verifier


def _response_with(content: str) -> mock.MagicMock:
    response = mock.MagicMock()
    response.content = content
    return response


def _valid_payload() -> dict[str, object]:
    return {
        "verdict": "PASS",
        "confidence": 0.9,
        "scores": {
            "correctness": 9,
            "completeness": 8,
            "quality": 9,
            "testing": 8,
            "risks": 7,
        },
        "concerns": [],
        "summary": "Looks good.",
    }


@pytest.mark.parametrize(
    "bad_content",
    [
        lambda payload: "Here you go:\n" + json.dumps(payload),
        lambda payload: "```json\n" + json.dumps(payload) + "\n```",
        lambda _payload: (
            '{"verdict": "PASS", "confidence": 0.9, "scores": '
            '{"correctness": 9, "completeness": 8, "quality": 9, "testing": 8, "risks": 7,}, '
            '"concerns": [], "summary": "Looks good.",}'
        ),
    ],
)
def test_evaluate_pr_repairs_malformed_output(monkeypatch: pytest.MonkeyPatch, bad_content) -> None:
    payload = _valid_payload()
    bad = bad_content(payload)
    good = json.dumps(payload)

    mock_client = mock.MagicMock()
    mock_client.invoke.side_effect = [_response_with(bad), _response_with(good)]

    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "prompt")
    monkeypatch.setattr(
        pr_verifier,
        "_get_llm_client",
        lambda model=None, provider=None: (mock_client, "github-models"),
    )

    result = pr_verifier.evaluate_pr("context")
    assert result.verdict == "PASS"
    assert result.used_llm is True
    assert mock_client.invoke.call_count == 2


def test_comparison_runner_repairs_malformed_output() -> None:
    payload = _valid_payload()
    bad = "```json\n" + json.dumps(payload) + "\n```"
    good = json.dumps(payload)

    mock_client = mock.MagicMock()
    mock_client.invoke.side_effect = [_response_with(bad), _response_with(good)]

    runner = pr_verifier.ComparisonRunner(
        context="context",
        diff=None,
        prompt="prompt",
        clients=[(mock_client, "github-models", "model")],
    )
    result = runner.run_single(mock_client, "github-models", "model")
    assert result.verdict == "PASS"
    assert result.used_llm is True
    assert mock_client.invoke.call_count == 2


def test_evaluate_pr_valid_output_no_repair(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    good = json.dumps(payload)

    mock_client = mock.MagicMock()
    mock_client.invoke.side_effect = [_response_with(good)]

    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "prompt")
    monkeypatch.setattr(
        pr_verifier,
        "_get_llm_client",
        lambda model=None, provider=None: (mock_client, "github-models"),
    )

    result = pr_verifier.evaluate_pr("context")
    assert result.verdict == "PASS"
    assert result.used_llm is True
    assert mock_client.invoke.call_count == 1


def test_evaluate_pr_repair_prompt_includes_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    bad = "Here you go:\n" + json.dumps(payload)
    good = json.dumps(payload)

    mock_client = mock.MagicMock()
    mock_client.invoke.side_effect = [_response_with(bad), _response_with(good)]

    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "prompt")
    monkeypatch.setattr(
        pr_verifier,
        "_get_llm_client",
        lambda model=None, provider=None: (mock_client, "github-models"),
    )

    result = pr_verifier.evaluate_pr("context")
    assert result.verdict == "PASS"
    assert result.used_llm is True
    assert mock_client.invoke.call_count == 2

    repair_prompt = mock_client.invoke.call_args_list[1].args[0]
    assert "Schema:" in repair_prompt
    assert "Validation errors:" in repair_prompt
    assert "Original response:" in repair_prompt
    assert "Here you go:" in repair_prompt
    assert '"verdict"' in repair_prompt


def test_evaluate_pr_repairs_once_then_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _valid_payload()
    bad = "```json\n" + json.dumps(payload) + "\n```"

    mock_client = mock.MagicMock()
    mock_client.invoke.side_effect = [_response_with(bad), _response_with(bad)]

    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "prompt")
    monkeypatch.setattr(
        pr_verifier,
        "_get_llm_client",
        lambda model=None, provider=None: (mock_client, "github-models"),
    )

    result = pr_verifier.evaluate_pr("context")
    assert result.verdict == "CONCERNS"
    assert result.used_llm is True
    assert result.error
    assert "Failed to parse JSON response after repair" in result.error
    assert mock_client.invoke.call_count == 2


def test_build_llm_config_includes_standard_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
    monkeypatch.setenv("GITHUB_RUN_ID", "555")
    context = "Pull request: [#123](https://github.com/octo/repo/pull/123)"

    config = pr_verifier._build_llm_config(operation="evaluate_pr", context=context)

    metadata = config["metadata"]
    assert metadata["repo"] == "octo/repo"
    assert metadata["run_id"] == "555"
    assert metadata["issue_or_pr_number"] == "123"
    assert metadata["operation"] == "evaluate_pr"
    assert metadata["pr_number"] == "123"
    assert metadata["issue_number"] is None

    tags = config["tags"]
    assert "workflows-agents" in tags
    assert "operation:evaluate_pr" in tags
    assert "repo:octo/repo" in tags
    assert "issue_or_pr:123" in tags
    assert "run_id:555" in tags


def test_invoke_llm_passes_config_metadata(llm_env_sentinel: dict[str, str]) -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def invoke(self, *args: object, **kwargs: object) -> object:
            self.calls.append(dict(kwargs))
            return object()

    client = DummyClient()
    context = "Pull request: [#321](https://github.com/sentinel/repo/pull/321)"

    response = pr_verifier._invoke_llm(
        client,
        "prompt",
        operation="evaluate_pr",
        context=context,
    )

    expected_metadata = {
        "repo": llm_env_sentinel["GITHUB_REPOSITORY"],
        "run_id": llm_env_sentinel["GITHUB_RUN_ID"],
        "issue_or_pr_number": "321",
        "operation": "evaluate_pr",
        "pr_number": "321",
        "issue_number": None,
    }
    expected_tags = [
        "workflows-agents",
        "operation:evaluate_pr",
        "repo:sentinel/repo",
        "issue_or_pr:321",
        "run_id:run-777",
    ]

    assert response is not None
    assert client.calls
    assert client.calls[0]["config"] == {"metadata": expected_metadata, "tags": expected_tags}


def test_evaluate_pr_passes_config_metadata(
    llm_env_sentinel: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.response = _response_with(json.dumps(_valid_payload()))

        def invoke(self, *args: object, **kwargs: object) -> object:
            self.calls.append(dict(kwargs))
            return self.response

    client = DummyClient()
    context = "Pull request: [#456](https://github.com/sentinel/repo/pull/456)"

    monkeypatch.setattr(pr_verifier, "_prepare_prompt", lambda ctx, diff: "prompt")
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda model=None, provider=None: (client, "openai"))

    result = pr_verifier.evaluate_pr(context)

    expected_metadata = {
        "repo": llm_env_sentinel["GITHUB_REPOSITORY"],
        "run_id": llm_env_sentinel["GITHUB_RUN_ID"],
        "issue_or_pr_number": "456",
        "operation": "evaluate_pr",
        "pr_number": "456",
        "issue_number": None,
    }
    expected_tags = [
        "workflows-agents",
        "operation:evaluate_pr",
        "repo:sentinel/repo",
        "issue_or_pr:456",
        "run_id:run-777",
    ]

    assert result.verdict == "PASS"
    assert client.calls[0]["config"] == {"metadata": expected_metadata, "tags": expected_tags}


def test_comparison_runner_passes_config_metadata(llm_env_sentinel: dict[str, str]) -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []
            self.response = _response_with(json.dumps(_valid_payload()))

        def invoke(self, *args: object, **kwargs: object) -> object:
            self.calls.append(dict(kwargs))
            return self.response

    client = DummyClient()
    context = "Pull request: [#456](https://github.com/sentinel/repo/pull/456)"
    runner = pr_verifier.ComparisonRunner(
        context=context,
        diff=None,
        prompt="prompt",
        clients=[(client, "openai", "o3-mini")],
    )

    result = runner.run_single(client, "openai", "o3-mini")

    expected_metadata = {
        "repo": llm_env_sentinel["GITHUB_REPOSITORY"],
        "run_id": llm_env_sentinel["GITHUB_RUN_ID"],
        "issue_or_pr_number": "456",
        "operation": "evaluate_pr_compare",
        "pr_number": "456",
        "issue_number": None,
    }
    expected_tags = [
        "workflows-agents",
        "operation:evaluate_pr_compare",
        "repo:sentinel/repo",
        "issue_or_pr:456",
        "run_id:run-777",
    ]

    assert result.verdict == "PASS"
    assert client.calls[0]["config"] == {"metadata": expected_metadata, "tags": expected_tags}
