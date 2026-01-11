#!/usr/bin/env python3
"""Ensure keepalive workflow timeout variables exist for a repository."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Iterable

import requests

DEFAULT_API_ROOT = "https://api.github.com"


class RepoVariableError(RuntimeError):
    """Raised when the GitHub API reports an unrecoverable error."""


@dataclass(frozen=True)
class VariableSpec:
    name: str
    value: str


def resolve_api_root(explicit: str | None = None) -> str:
    candidate = (explicit or os.getenv("GITHUB_API_URL") or DEFAULT_API_ROOT).strip()
    if not candidate:
        return DEFAULT_API_ROOT
    return candidate.rstrip("/")


def require_token(explicit: str | None = None) -> str:
    if explicit:
        candidate = explicit.strip()
        if candidate:
            return candidate
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        raise RepoVariableError(
            "Set the GITHUB_TOKEN (or GH_TOKEN) environment variable with a token that can manage repository variables."
        )
    return token


def _build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "workflows-timeout-variables",
        }
    )
    return session


def _variables_url(repo: str, *, api_root: str) -> str:
    return f"{api_root}/repos/{repo}/actions/variables"


def _variable_url(repo: str, name: str, *, api_root: str) -> str:
    return f"{api_root}/repos/{repo}/actions/variables/{name}"


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return (response.text or "").strip()


def build_timeout_variables(default_minutes: int, extended_minutes: int) -> list[VariableSpec]:
    return [
        VariableSpec("WORKFLOW_TIMEOUT_DEFAULT", str(default_minutes)),
        VariableSpec("WORKFLOW_TIMEOUT_EXTENDED", str(extended_minutes)),
    ]


def fetch_repo_variables(
    session: requests.Session,
    repo: str,
    names: Iterable[str],
    *,
    api_root: str,
) -> dict[str, str]:
    wanted = {name.strip() for name in names if name}
    if not wanted:
        return {}

    results: dict[str, str] = {}
    page = 1
    per_page = 100
    url = _variables_url(repo, api_root=api_root)

    while True:
        response = session.get(url, params={"per_page": per_page, "page": page}, timeout=30)
        if response.status_code != 200:
            raise RepoVariableError(
                f"Failed to list repository variables: {response.status_code} {_response_message(response)}"
            )
        payload = response.json()
        variables = payload.get("variables", [])
        for variable in variables:
            name = str(variable.get("name", "")).strip()
            if not name or name not in wanted:
                continue
            value = variable.get("value")
            if value is None:
                continue
            results[name] = str(value)
        if len(variables) < per_page or len(results) == len(wanted):
            break
        page += 1

    return results


def plan_variable_updates(
    desired: Iterable[VariableSpec], existing: dict[str, str]
) -> tuple[list[VariableSpec], list[VariableSpec]]:
    to_create: list[VariableSpec] = []
    to_update: list[VariableSpec] = []

    for spec in desired:
        current = existing.get(spec.name)
        if current is None:
            to_create.append(spec)
        elif str(current) != spec.value:
            to_update.append(spec)

    return to_create, to_update


def apply_variable_updates(
    session: requests.Session,
    repo: str,
    *,
    api_root: str,
    to_create: Iterable[VariableSpec],
    to_update: Iterable[VariableSpec],
) -> None:
    base_url = _variables_url(repo, api_root=api_root)
    for spec in to_create:
        response = session.post(
            base_url,
            json={"name": spec.name, "value": spec.value},
            timeout=30,
        )
        if response.status_code not in {201, 204}:
            raise RepoVariableError(
                f"Failed to create {spec.name}: {response.status_code} {_response_message(response)}"
            )

    for spec in to_update:
        response = session.patch(
            _variable_url(repo, spec.name, api_root=api_root),
            json={"name": spec.name, "value": spec.value},
            timeout=30,
        )
        if response.status_code not in {200, 204}:
            raise RepoVariableError(
                f"Failed to update {spec.name}: {response.status_code} {_response_message(response)}"
            )


def describe_plan(
    to_create: Iterable[VariableSpec], to_update: Iterable[VariableSpec]
) -> list[str]:
    lines: list[str] = []
    for spec in to_create:
        lines.append(f"create {spec.name}={spec.value}")
    for spec in to_update:
        lines.append(f"update {spec.name}={spec.value}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure keepalive workflow timeout variables exist in a repository.",
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY"),
        help="Repository in the form owner/name. Defaults to GITHUB_REPOSITORY.",
    )
    parser.add_argument(
        "--default-minutes",
        type=int,
        default=int(os.getenv("WORKFLOW_TIMEOUT_DEFAULT", "45")),
        help="Default timeout in minutes. Defaults to WORKFLOW_TIMEOUT_DEFAULT or 45.",
    )
    parser.add_argument(
        "--extended-minutes",
        type=int,
        default=int(os.getenv("WORKFLOW_TIMEOUT_EXTENDED", "90")),
        help="Extended timeout in minutes. Defaults to WORKFLOW_TIMEOUT_EXTENDED or 90.",
    )
    parser.add_argument(
        "--token",
        help="Token for GitHub API access. Defaults to GITHUB_TOKEN or GH_TOKEN.",
    )
    parser.add_argument(
        "--api-url",
        help="GitHub API base URL. Defaults to GITHUB_API_URL or https://api.github.com.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes instead of dry run.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with a non-zero status if changes are needed.",
    )
    args = parser.parse_args(argv)

    if args.apply and args.check:
        parser.error("--check cannot be combined with --apply.")

    if not args.repo:
        parser.error("--repo is required when GITHUB_REPOSITORY is not set.")

    desired = build_timeout_variables(args.default_minutes, args.extended_minutes)
    api_root = resolve_api_root(args.api_url)

    try:
        token = require_token(args.token)
        session = _build_session(token)
        existing = fetch_repo_variables(
            session,
            args.repo,
            [spec.name for spec in desired],
            api_root=api_root,
        )
        to_create, to_update = plan_variable_updates(desired, existing)
        plan_lines = describe_plan(to_create, to_update)
        if plan_lines:
            print(f"Repository: {args.repo}")
            for line in plan_lines:
                print(f"- {line}")
        else:
            print(f"Repository: {args.repo}")
            print("No changes required.")

        if args.apply and plan_lines:
            apply_variable_updates(
                session,
                args.repo,
                api_root=api_root,
                to_create=to_create,
                to_update=to_update,
            )
            print("Updates applied.")
        elif args.check and plan_lines:
            return 1
    except RepoVariableError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
