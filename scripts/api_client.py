from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 30


def _request_json(method: str, url: str, token: str, payload: dict[str, Any] | None) -> Any:
    response = requests.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=DEFAULT_TIMEOUT,
    )
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f"GitHub API error {response.status_code}: {detail}")
    if response.status_code == 204:
        return None
    return response.json()


def _build_url(base_url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params)}"


def fetch_issue(repo: str, issue_number: int, token: str):
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    data = _request_json("GET", url, token, payload=None)
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
    per_page: int = 100,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"state": "open", "page": page, "per_page": per_page}
    if labels:
        params["labels"] = ",".join(labels)
    url = _build_url(f"{GITHUB_API}/repos/{repo}/issues", params)
    data = _request_json("GET", url, token, payload=None)
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issues.")
    return data


def fetch_issue_comments(repo: str, issue_number: int, token: str) -> list[dict[str, Any]]:
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments?per_page=100"
    data = _request_json("GET", url, token, payload=None)
    if not isinstance(data, list):
        raise RuntimeError("GitHub API did not return a JSON array for issue comments.")
    return data


def create_issue(
    repo: str,
    token: str,
    title: str,
    body: str | None,
    labels: list[str] | None,
) -> dict[str, Any]:
    url = f"{GITHUB_API}/repos/{repo}/issues"
    from scripts.duplicate_detection import build_issue_payload

    payload = build_issue_payload(title, body, labels)
    data = _request_json("POST", url, token, payload=payload)
    if not isinstance(data, dict):
        raise RuntimeError("GitHub API did not return a JSON object for the issue.")
    return data
