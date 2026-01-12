from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF = 1.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


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


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        delay = float(raw)
    except ValueError:
        return None
    if delay <= 0:
        return None
    return delay


def _parse_rate_limit_reset(headers: dict[str, str], now: float) -> float | None:
    remaining = headers.get("X-RateLimit-Remaining")
    reset_raw = headers.get("X-RateLimit-Reset")
    if remaining is None or reset_raw is None:
        return None
    if str(remaining).strip() != "0":
        return None
    try:
        reset_at = float(reset_raw)
    except ValueError:
        return None
    delay = max(0.0, reset_at - now)
    if delay <= 0:
        return None
    return delay


def _resolve_retry_delay(
    backoff: float,
    attempt: int,
    response: requests.Response | None,
) -> float:
    if response is not None:
        retry_after = _parse_retry_after(response.headers)
        if retry_after is not None:
            return retry_after
        rate_limit_delay = _parse_rate_limit_reset(response.headers, time.time())
        if rate_limit_delay is not None:
            return rate_limit_delay
    if backoff <= 0:
        return 0.0
    return backoff * (2 ** (attempt - 1))


def _sleep_with_backoff(
    backoff: float,
    attempt: int,
    response: requests.Response | None = None,
) -> None:
    delay = _resolve_retry_delay(backoff, attempt, response)
    if delay <= 0:
        return
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
    max_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff: float = DEFAULT_RETRY_BACKOFF,
    stream: bool = False,
) -> requests.Response:
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            request_kwargs = {
                "headers": {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
                "json": payload,
                "timeout": DEFAULT_TIMEOUT,
            }
            if stream:
                request_kwargs["stream"] = True
            response = requests.request(method, url, **request_kwargs)
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
                _sleep_with_backoff(backoff, attempt, response)
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
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
):
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
    from scripts.duplicate_detection import parse_source_issue

    return parse_source_issue(data)


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
    from scripts.duplicate_detection import build_issue_payload

    payload = build_issue_payload(title, body, labels)
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
) -> set[str] | None:
    response = _request_response(
        "GET",
        GITHUB_API,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    scopes_header = response.headers.get("X-OAuth-Scopes")
    if scopes_header is None:
        return None
    scopes = {scope.strip() for scope in scopes_header.split(",") if scope.strip()}
    return scopes


def fetch_artifacts_page(
    repo: str,
    token: str,
    *,
    page: int,
    per_page: int = 100,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> dict[str, Any]:
    params = {"page": page, "per_page": per_page}
    url = _build_url(f"{GITHUB_API}/repos/{repo}/actions/artifacts", params)
    data = _request_json(
        "GET",
        url,
        token,
        payload=None,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for artifacts.")
    return data


def download_artifact_zip(
    repo: str,
    artifact_id: int,
    token: str,
    dest_path: str | Path,
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> None:
    url = f"{GITHUB_API}/repos/{repo}/actions/artifacts/{artifact_id}/zip"
    response = _request_response(
        "GET",
        url,
        token,
        payload=None,
        stream=True,
        **_retry_kwargs(retry_attempts, retry_backoff),
    )
    path = Path(dest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)
