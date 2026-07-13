from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol, cast
from urllib.parse import urlencode

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF = 1.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class _RequestsModule(Protocol):
    RequestException: type[Exception]

    def request(self, method: str, url: str, **kwargs: Any) -> _Response: ...


requests = cast(_RequestsModule, importlib.import_module("requests"))


def _should_retry(status_code: int, detail: Any) -> bool:
    if status_code in RETRY_STATUS_CODES:
        return True
    if status_code == 403:
        message = ""
        if isinstance(detail, dict):
            message = str(detail.get("message") or "")
        else:
            message = str(detail or "")
        if "rate limit" in message.lower():
            return True
    return False


def _sleep_with_backoff(backoff: float, attempt: int) -> None:
    if backoff <= 0:
        return
    delay = backoff * (2 ** (attempt - 1))
    time.sleep(delay)


def _request_json(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None,
    *,
    max_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff: float = DEFAULT_RETRY_BACKOFF,
) -> Any:
    response = _request_response(
        method,
        url,
        token,
        payload,
        max_attempts=max_attempts,
        backoff=backoff,
    )
    if response.status_code == 204:
        return None
    return response.json()


def _request_response(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None,
    *,
    accept: str = "application/vnd.github+json",
    max_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff: float = DEFAULT_RETRY_BACKOFF,
) -> _Response:
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            request_kwargs: dict[str, Any] = {
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "Accept": accept,
                },
                "timeout": DEFAULT_TIMEOUT,
            }
            if payload is not None:
                request_kwargs["json"] = payload
            response = requests.request(
                method,
                url,
                **request_kwargs,
            )
        except requests.RequestException as exc:
            if attempt >= attempts:
                raise RuntimeError("GitHub API request failed.") from exc
            _sleep_with_backoff(backoff, attempt)
            continue

        if response.status_code >= 400:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            if _should_retry(response.status_code, detail) and attempt < attempts:
                _sleep_with_backoff(backoff, attempt)
                continue
            raise RuntimeError(f"GitHub API error {response.status_code}: {detail}")

        return response

    raise RuntimeError("GitHub API request failed after retries.")


def _retry_kwargs(
    retry_attempts: int | None,
    retry_backoff: float | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if retry_attempts is not None:
        kwargs["max_attempts"] = retry_attempts
    if retry_backoff is not None:
        kwargs["backoff"] = retry_backoff
    return kwargs


def _build_url(base_url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params)}"


def fetch_issue(
    repo: str,
    issue_number: int,
    token: str,
    *,
    parser: Callable[[dict[str, Any]], Any] | None = None,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> Any:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    data = _request_json(
        "GET",
        url,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the issue.")
    if parser is not None:
        return parser(data)
    return data


def fetch_pull_request(
    repo: str,
    pull_number: int,
    token: str,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> dict[str, Any]:
    """Fetch pull-request metadata through the shared retrying API client."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pull_number}"
    data = _request_json(
        "GET",
        url,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the pull request.")
    return data


def fetch_pull_request_diff(
    repo: str,
    pull_number: int,
    token: str,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> str:
    """Fetch a pull-request diff through the shared retrying API client."""
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pull_number}"
    response = _request_response(
        "GET",
        url,
        token,
        payload=None,
        accept="application/vnd.github.diff",
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    return response.text


def fetch_issues(
    repo: str,
    token: str,
    *,
    labels: list[str] | None,
    page: int,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
    per_page: int = 100,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"state": "open", "page": page, "per_page": per_page}
    if labels:
        params["labels"] = ",".join(labels)
    url = _build_url(f"{GITHUB_API}/repos/{repo}/issues", params)
    data = _request_json(
        "GET",
        url,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issues.")
    return data


def fetch_issue_comments(
    repo: str,
    issue_number: int,
    token: str,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> list[dict[str, Any]]:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments?per_page=100"
    data = _request_json(
        "GET",
        url,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issue comments.")
    return data


def create_issue(
    repo: str,
    token: str,
    title: str,
    body: str | None,
    labels: list[str] | None,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> dict[str, Any]:
    url = f"{GITHUB_API}/repos/{repo}/issues"
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    data = _request_json(
        "POST",
        url,
        token,
        payload=payload,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the issue.")
    return data


def fetch_oauth_scopes(
    token: str,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> str | None:
    try:
        response = _request_response(
            "GET",
            GITHUB_API,
            token,
            payload=None,
            **_retry_kwargs(retry_attempts, retry_backoff),
        )
    except RuntimeError:
        return None
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    scopes = headers.get("X-OAuth-Scopes")
    return str(scopes) if scopes is not None else None
