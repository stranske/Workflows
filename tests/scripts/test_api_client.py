from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from scripts import api_client


class FakeRequestException(Exception):
    pass


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        json_error: bool = False,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.headers = headers
        self.json_error = json_error
        self.json_calls = 0

    def json(self) -> Any:
        self.json_calls += 1
        if self.json_error:
            raise ValueError("not json")
        return self._payload


class FakeRequests:
    RequestException = FakeRequestException

    def __init__(self, *effects: FakeResponse | BaseException) -> None:
        self.effects = list(effects)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        effect = self.effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def install_fake_requests(
    monkeypatch: pytest.MonkeyPatch, *effects: FakeResponse | BaseException
) -> FakeRequests:
    fake = FakeRequests(*effects)
    monkeypatch.setattr(api_client, "requests", fake)
    monkeypatch.setattr(api_client.time, "sleep", lambda delay: None)
    return fake


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_should_retry_retryable_statuses(status_code: int) -> None:
    assert api_client._should_retry(status_code, None) is True


def test_should_retry_rate_limit_403_message_only() -> None:
    assert api_client._should_retry(403, {"message": "API rate limit exceeded"}) is True
    assert api_client._should_retry(403, "rate limit exceeded") is True
    assert api_client._should_retry(403, {"error": "rate limit exceeded"}) is False
    assert api_client._should_retry(403, {"message": "forbidden"}) is False


@pytest.mark.parametrize("status_code", [200, 201, 400, 401, 404])
def test_should_retry_non_retryable_statuses(status_code: int) -> None:
    assert api_client._should_retry(status_code, {"message": "error"}) is False


def test_build_url_handles_empty_and_encoded_params() -> None:
    base = "https://api.github.com/search/issues"

    assert api_client._build_url(base, None) == base
    assert api_client._build_url(base, {}) == base
    assert (
        api_client._build_url(base, {"q": "label:bug is:open", "page": 2})
        == "https://api.github.com/search/issues?q=label%3Abug+is%3Aopen&page=2"
    )


def test_request_response_success_sets_headers_timeout_and_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(payload={"ok": True})
    fake = install_fake_requests(monkeypatch, response)

    result = api_client._request_response("POST", "https://api.github.com/test", "tok", {"x": 1})

    assert result is response
    method, url, kwargs = fake.calls[0]
    assert method == "POST"
    assert url == "https://api.github.com/test"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["headers"]["Accept"] == "application/vnd.github+json"
    assert kwargs["timeout"] == api_client.DEFAULT_TIMEOUT
    assert kwargs["json"] == {"x": 1}


def test_request_response_raises_final_http_error_with_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_requests(
        monkeypatch,
        FakeResponse(status_code=404, text="Not found", json_error=True),
    )

    with pytest.raises(RuntimeError, match="GitHub API error 404: Not found"):
        api_client._request_response(
            "GET", "https://api.github.com/test", "tok", None, max_attempts=1
        )


def test_request_response_retries_retryable_http_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(
        monkeypatch,
        FakeResponse(status_code=503, payload={"message": "try later"}),
        FakeResponse(status_code=200, payload={"ok": True}),
    )

    result = api_client._request_response(
        "GET", "https://api.github.com/test", "tok", None, max_attempts=2, backoff=0
    )

    assert result.status_code == 200
    assert len(fake.calls) == 2


def test_request_response_retries_request_exception_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(
        monkeypatch,
        FakeRequestException("connection reset"),
        FakeResponse(status_code=200, payload={"ok": True}),
    )

    result = api_client._request_response(
        "GET", "https://api.github.com/test", "tok", None, max_attempts=2, backoff=0
    )

    assert result.status_code == 200
    assert len(fake.calls) == 2


def test_request_response_raises_final_request_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_requests(monkeypatch, FakeRequestException("connection reset"))

    with pytest.raises(RuntimeError, match="GitHub API request failed"):
        api_client._request_response(
            "GET", "https://api.github.com/test", "tok", None, max_attempts=1
        )


def test_request_json_returns_none_for_204_without_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(status_code=204, payload={"unused": True})
    install_fake_requests(monkeypatch, response)

    assert api_client._request_json("DELETE", "https://api.github.com/test", "tok", None) is None
    assert response.json_calls == 0


def test_request_json_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_requests(monkeypatch, FakeResponse(status_code=200, payload={"ok": True}))

    assert api_client._request_json("GET", "https://api.github.com/test", "tok", None) == {
        "ok": True
    }


def test_retry_kwargs_omits_missing_values() -> None:
    assert api_client._retry_kwargs(None, None) == {}
    assert api_client._retry_kwargs(5, None) == {"max_attempts": 5}
    assert api_client._retry_kwargs(None, 0.5) == {"backoff": 0.5}
    assert api_client._retry_kwargs(5, 0.5) == {"max_attempts": 5, "backoff": 0.5}


def test_fetch_issue_validates_shape_and_applies_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(monkeypatch, FakeResponse(payload={"number": 12, "title": "T"}))

    assert api_client.fetch_issue("owner/repo", 12, "tok", parser=lambda data: data["title"]) == "T"
    assert fake.calls[0][1] == "https://api.github.com/repos/owner/repo/issues/12"

    install_fake_requests(monkeypatch, FakeResponse(payload=[]))
    with pytest.raises(RuntimeError, match="JSON object for the issue"):
        api_client.fetch_issue("owner/repo", 12, "tok")


def test_fetch_pull_request_and_diff_use_shared_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_client, "_request_json", lambda *args, **kwargs: {"title": "PR"})
    response = SimpleNamespace(text="diff --git a/a b/a")
    calls: list[dict[str, object]] = []

    def fake_response(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return response

    monkeypatch.setattr(api_client, "_request_response", fake_response)

    assert api_client.fetch_pull_request("owner/repo", 7, "tok") == {"title": "PR"}
    assert api_client.fetch_pull_request_diff("owner/repo", 7, "tok") == response.text
    assert calls == [{"payload": None, "accept": "application/vnd.github.v3.diff"}]


def test_fetch_pull_request_rejects_nonobject_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_client, "_request_json", lambda *args, **kwargs: ["not", "an", "object"]
    )

    with pytest.raises(RuntimeError, match="JSON object for the pull request"):
        api_client.fetch_pull_request("owner/repo", 7, "tok")


def test_fetch_issues_validates_shape_and_encodes_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(monkeypatch, FakeResponse(payload=[{"number": 1}]))

    assert api_client.fetch_issues("owner/repo", "tok", labels=["bug", "help wanted"], page=3) == [
        {"number": 1}
    ]
    assert (
        fake.calls[0][1]
        == "https://api.github.com/repos/owner/repo/issues?state=open&page=3&per_page=100&labels=bug%2Chelp+wanted"
    )

    install_fake_requests(monkeypatch, FakeResponse(payload={"not": "a list"}))
    with pytest.raises(RuntimeError, match="JSON array for issues"):
        api_client.fetch_issues("owner/repo", "tok", labels=None, page=1)


def test_fetch_issue_comments_validates_shape_and_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(monkeypatch, FakeResponse(payload=[{"body": "hi"}]))

    assert api_client.fetch_issue_comments("owner/repo", 7, "tok") == [{"body": "hi"}]
    assert (
        fake.calls[0][1] == "https://api.github.com/repos/owner/repo/issues/7/comments?per_page=100"
    )

    install_fake_requests(monkeypatch, FakeResponse(payload={"not": "a list"}))
    with pytest.raises(RuntimeError, match="JSON array for issue comments"):
        api_client.fetch_issue_comments("owner/repo", 7, "tok")


def test_create_issue_builds_payload_and_validates_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_requests(monkeypatch, FakeResponse(status_code=201, payload={"number": 3}))

    assert api_client.create_issue("owner/repo", "tok", "Title", "Body", ["bug"]) == {"number": 3}
    assert fake.calls[0][0] == "POST"
    assert fake.calls[0][1] == "https://api.github.com/repos/owner/repo/issues"
    assert fake.calls[0][2]["json"] == {
        "title": "Title",
        "body": "Body",
        "labels": ["bug"],
    }

    install_fake_requests(monkeypatch, FakeResponse(status_code=201, payload=[]))
    with pytest.raises(RuntimeError, match="JSON object for the issue"):
        api_client.create_issue("owner/repo", "tok", "Title", None, None)


def test_fetch_oauth_scopes_handles_headers_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_requests(
        monkeypatch,
        FakeResponse(headers={"X-OAuth-Scopes": "repo, workflow"}),
    )
    assert api_client.fetch_oauth_scopes("tok") == "repo, workflow"

    install_fake_requests(monkeypatch, FakeResponse(headers={}))
    assert api_client.fetch_oauth_scopes("tok") is None

    install_fake_requests(monkeypatch, FakeRequestException("connection reset"))
    assert api_client.fetch_oauth_scopes("tok", retry_attempts=1) is None
