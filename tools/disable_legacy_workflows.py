"""Lightweight stub for disabling legacy workflows."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

WORKFLOW_DIR = Path(".github/workflows")


def _normalized_slug(path: Path) -> str:
    name = path.name
    if name.endswith(".yml.disabled"):
        return name[: -len(".disabled")]
    return name


def _extract_workflow_name(path: Path) -> str:
    contents = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(contents)
    except yaml.YAMLError:
        data = None
    if isinstance(data, dict):
        name = data.get("name")
        if name:
            return str(name).strip()

    for line in contents.splitlines():
        if line.startswith("name:"):
            value = line.split(":", 1)[1].strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value
    return ""


CANONICAL_WORKFLOW_FILES = {_normalized_slug(path) for path in WORKFLOW_DIR.glob("*.yml*")}
CANONICAL_WORKFLOW_NAMES = {
    name for path in WORKFLOW_DIR.glob("*.yml*") if (name := _extract_workflow_name(path))
}


@dataclass
class WorkflowAPIError(Exception):
    status_code: int
    reason: str
    url: str
    body: str

    def __str__(self) -> str:
        return json.dumps(
            {
                "status_code": self.status_code,
                "reason": self.reason,
                "url": self.url,
                "body": self.body,
            }
        )


def _extract_next_link(header: str | None) -> str | None:
    if not header:
        return None
    for segment in header.split(","):
        parts = segment.split(";")
        if len(parts) < 2:
            continue
        url = parts[0].strip().strip("<>")
        for part in parts[1:]:
            if 'rel="next"' in part:
                return url
    return None


def _normalize_allowlist(values: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        for token in value.split(","):
            token = token.strip()
            if token:
                normalized.add(token)
    return normalized


def _list_all_workflows(
    base_url: str, headers: dict[str, str]
) -> list[dict[str, object]]:  # noqa: ARG001
    return []


def _http_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    data: bytes | None = None,
) -> tuple[bytes, dict[str, str]]:  # noqa: ARG001
    return b"", {}


def disable_legacy_workflows(
    *,
    repository: str,
    token: str,
    dry_run: bool,
    extra_allow: Iterable[str] = (),
) -> dict[str, list[str]]:
    allowlist = CANONICAL_WORKFLOW_FILES | _normalize_allowlist(extra_allow)
    workflows = _list_all_workflows(
        f"https://api.github.com/repos/{repository}/actions/workflows",
        headers={"Authorization": f"Bearer {token}"},
    )

    summary = {"disabled": [], "kept": [], "skipped": []}
    for workflow in workflows:
        name = str(workflow.get("name", ""))
        path = str(workflow.get("path", ""))
        slug = Path(path).stem
        if f"{slug}.yml" in allowlist:
            summary["kept"].append(name)
            continue
        try:
            if not dry_run:
                _http_request(
                    "PUT",
                    f"https://api.github.com/repos/{repository}/actions/workflows/{workflow.get('id')}/disable",
                    headers={"Authorization": f"Bearer {token}"},
                )
            summary["disabled"].append(name)
        except WorkflowAPIError:
            summary["skipped"].append(f"(unsupported) {name} ({Path(path).stem})")
    return summary
