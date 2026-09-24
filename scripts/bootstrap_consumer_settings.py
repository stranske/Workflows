#!/usr/bin/env python3
"""Automate fresh-consumer bootstrap settings, labels, and fleet health via gh CLI.

Registering a new first-party consumer requires several manual GitHub-settings
steps (see ``templates/consumer-repo/docs/SETUP_CHECKLIST.md`` sections 3.1,
3.3, and 3.3.1) that are easy to skip silently. Skipping them produces distinct
hard failures:

* 3.3.1 - leaving ``default_workflow_permissions`` at GitHub's ``read`` default
  makes every reusable-calling workflow (Gate, ``ci.yml``) hit ``startup_failure``
  before any job runs.
* 3.3 - missing repo variables ``USE_CONSOLIDATED_WORKFLOWS`` /
  ``ALLOWED_KEEPALIVE_LOGINS`` leave keepalive skipped, so the coder is never
  dispatched.
* 3.1 - ``stranske-automation-bot`` not a collaborator means no push access for
  autofix commits / agent branches.

This script builds the exact ``gh`` commands that perform those toggles. It is
dry-run by default (prints the commands) and only mutates state when
``--execute`` is passed, mirroring ``scripts/create_verifier_labels.py``.

Usage::

  python scripts/bootstrap_consumer_settings.py --repo stranske/Foo
  python scripts/bootstrap_consumer_settings.py --repo stranske/Foo --execute
  python scripts/bootstrap_consumer_settings.py --repo stranske/Foo --check
  python scripts/bootstrap_consumer_settings.py --repo stranske/Foo --verify
  python scripts/bootstrap_consumer_settings.py --repo stranske/Foo --labels-only --execute
  python scripts/bootstrap_consumer_settings.py --health-check
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.list_registered_consumer_repos import extract_repos
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution.
    from list_registered_consumer_repos import extract_repos  # type: ignore[no-redef]

DEFAULT_BOT = "stranske-automation-bot"
USE_CONSOLIDATED_WORKFLOWS_VALUE = "true"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_MANIFEST = REPO_ROOT / ".github/workflows/maint-68-sync-consumer-repos.yml"
PRIORITY_LABELS = {
    "priority:high": {
        "color": "b60205",
        "description": "High-priority weekly repo-review work",
    },
    "priority:normal": {
        "color": "fbca04",
        "description": "Normal-priority weekly repo-review work",
    },
    "priority:low": {
        "color": "0e8a16",
        "description": "Low-priority weekly repo-review work",
    },
}
SYSTEMIC_API_ERROR_MARKERS = (
    "bad credentials",
    "requires authentication",
    "rate limit",
    "secondary rate limit",
)
REPO_COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``owner/name`` into its parts, raising on malformed input."""
    parts = repo.strip().split("/")
    if (
        len(parts) != 2
        or not all(parts)
        or not all(REPO_COMPONENT_RE.fullmatch(part) for part in parts)
    ):
        raise SystemExit(f"Repo must be in 'owner/name' form, got: {repo!r}")
    return parts[0], parts[1]


def _default_keepalive_logins(repo: str) -> str:
    """The repo owner is the safe default keepalive-allowed login."""
    owner, _ = _split_repo(repo)
    return owner


def _workflow_permissions_command(repo: str) -> list[str]:
    """3.3.1 - grant write workflow permissions + PR approval."""
    return [
        "gh",
        "api",
        "--method",
        "PUT",
        f"/repos/{repo}/actions/permissions/workflow",
        "-F",
        "default_workflow_permissions=write",
        "-F",
        "can_approve_pull_request_reviews=true",
    ]


def _variable_command(repo: str, name: str, value: str) -> list[str]:
    """3.3 - set a required repo variable."""
    return [
        "gh",
        "variable",
        "set",
        name,
        "--repo",
        repo,
        "--body",
        value,
    ]


def _collaborator_command(repo: str, bot: str) -> list[str]:
    """3.1 - invite the service bot as a push collaborator."""
    return [
        "gh",
        "api",
        "--method",
        "PUT",
        f"/repos/{repo}/collaborators/{bot}",
        "-f",
        "permission=push",
    ]


def _workflow_permissions_check_command(repo: str) -> list[str]:
    return ["gh", "api", f"/repos/{repo}/actions/permissions/workflow"]


def _collaborator_check_command(repo: str, bot: str) -> list[str]:
    """Check whether bot is already a collaborator (gh returns non-zero if not)."""
    return ["gh", "api", f"/repos/{repo}/collaborators/{bot}"]


def _variable_list_command(repo: str) -> list[str]:
    return ["gh", "variable", "list", "--repo", repo, "--json", "name,value"]


def _label_create_command(repo: str, name: str, definition: dict[str, str]) -> list[str]:
    """Create one required label without overwriting existing metadata."""
    return [
        "gh",
        "label",
        "create",
        name,
        "--repo",
        repo,
        "--color",
        definition["color"],
        "--description",
        definition["description"],
    ]


def build_label_plan(repo: str) -> list[dict[str, object]]:
    """Build the three load-bearing priority-label operations."""
    _split_repo(repo)
    return [
        {
            "id": f"label_{name.removeprefix('priority:')}",
            "description": f"ensure {name} exists for opener selection",
            "command": _label_create_command(repo, name, definition),
        }
        for name, definition in PRIORITY_LABELS.items()
    ]


def _read_paginated_collection(endpoint: str) -> list[dict[str, Any]]:
    """Read every REST page and reject malformed or partial-looking payloads."""
    proc = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON list from {endpoint}")
    if not payload:
        return []
    if all(isinstance(page, list) for page in payload):
        items = [item for page in payload for item in page]
    elif all(isinstance(item, dict) for item in payload):
        items = payload
    else:
        raise ValueError(f"Malformed paginated JSON from {endpoint}")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError(f"Non-object item returned from {endpoint}")
    return items


def _priority_label_inventory(repo: str) -> dict[str, dict[str, Any]]:
    labels = _read_paginated_collection(f"/repos/{repo}/labels?per_page=100")
    inventory: dict[str, dict[str, Any]] = {}
    for label in labels:
        name = label.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"Malformed label payload for {repo}")
        inventory[name.lower()] = label
    return inventory


def _priority_label_findings(
    inventory: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    mismatched: list[str] = []
    for name, definition in PRIORITY_LABELS.items():
        current = inventory.get(name)
        if current is None:
            missing.append(name)
            continue
        color = str(current.get("color", "")).lower()
        description = current.get("description") or ""
        if color != definition["color"] or description != definition["description"]:
            mismatched.append(name)
    return missing, mismatched


def apply_priority_labels(repo: str) -> None:
    """Create only absent labels, then verify exact metadata without silent overwrite."""
    inventory = _priority_label_inventory(repo)
    missing, mismatched = _priority_label_findings(inventory)
    if mismatched:
        raise SystemExit(f"Refusing to overwrite label metadata in {repo}: {', '.join(mismatched)}")
    for name in missing:
        try:
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
            subprocess.run(
                _label_create_command(repo, name, PRIORITY_LABELS[name]),
                check=True,
            )
        except subprocess.CalledProcessError:
            # A concurrent creator is safe only when a fresh read proves exact metadata.
            current = _priority_label_inventory(repo)
            still_missing, now_mismatched = _priority_label_findings(current)
            if name in still_missing or name in now_mismatched:
                raise
    final_inventory = _priority_label_inventory(repo)
    final_missing, final_mismatched = _priority_label_findings(final_inventory)
    if final_missing or final_mismatched:
        details = final_missing + [f"{name} (metadata)" for name in final_mismatched]
        raise SystemExit(f"Priority label verification failed for {repo}: {', '.join(details)}")


def _issue_labels(issue: dict[str, Any]) -> set[str]:
    raw_labels = issue.get("labels")
    if not isinstance(raw_labels, list):
        raise ValueError("Issue labels must be a list")
    names: set[str] = set()
    for label in raw_labels:
        name = (
            label
            if isinstance(label, str)
            else label.get("name") if isinstance(label, dict) else None
        )
        if not isinstance(name, str):
            raise ValueError("Issue label entry is malformed")
        names.add(name.lower())
    return names


def _non_implementation_reason(issue: dict[str, Any]) -> str | None:
    if "pull_request" in issue:
        return "pull_request"
    title = issue.get("title")
    if not isinstance(title, str):
        raise ValueError("Issue title is missing")
    labels = _issue_labels(issue)
    lowered = title.lower()
    if "tracker:durable" in labels or "evidence-collection" in labels:
        return "durable_holder"
    if lowered.startswith("dependency dashboard"):
        return "dependency_dashboard"
    if "agent-metrics" in labels and "weekly" in lowered:
        return "agent_metrics_holder"
    user = issue.get("user") or {}
    login = str(user.get("login", "")).lower() if isinstance(user, dict) else ""
    if login.startswith("dependabot") and lowered.startswith(("bump ", "build(deps", "chore(deps")):
        return "dependency_bot"
    if "sync-generated" in labels:
        return "sync_bookkeeping"
    if lowered.startswith("[sync-review]") and {"automation", "consumer-sync"}.issubset(labels):
        return "sync_bookkeeping"
    return None


def summarize_implementation_issues(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """Count delivery issues without making priority a condition of existence."""
    implementation_count = 0
    priority_labelled_count = 0
    excluded: Counter[str] = Counter()
    required_names = set(PRIORITY_LABELS)
    for issue in issues:
        reason = _non_implementation_reason(issue)
        if reason:
            excluded[reason] += 1
            continue
        implementation_count += 1
        if _issue_labels(issue) & required_names:
            priority_labelled_count += 1
    return {
        "implementation_count": implementation_count,
        "priority_labelled_count": priority_labelled_count,
        "unprioritized_count": implementation_count - priority_labelled_count,
        "excluded": dict(sorted(excluded.items())),
    }


def _systemic_api_failure(error: BaseException) -> bool:
    stderr = str(getattr(error, "stderr", "") or "").lower()
    return any(marker in stderr for marker in SYSTEMIC_API_ERROR_MARKERS)


def check_consumer_health(repos: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Audit opener-reachability labels and issue counts for registered consumers."""
    if not repos:
        raise SystemExit("Registered consumer list is empty; refusing a healthy result.")
    for repo in repos:
        _split_repo(repo)

    rows: list[dict[str, Any]] = []
    global_error: str | None = None
    for repo in repos:
        row: dict[str, Any] = {
            "repository": repo,
            "implementation_count": None,
            "priority_labelled_count": None,
            "unprioritized_count": None,
            "missing": None,
            "metadata_mismatch": None,
            "excluded": {},
            "error": global_error,
        }
        if global_error is not None:
            row["status"] = "ERROR"
            rows.append(row)
            continue
        try:
            inventory = _priority_label_inventory(repo)
            missing, mismatched = _priority_label_findings(inventory)
            row["missing"] = missing
            row["metadata_mismatch"] = mismatched
        except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as error:
            row["error"] = f"label read failed: {error}"
            if _systemic_api_failure(error):
                global_error = row["error"]
        if global_error is None:
            try:
                issues = _read_paginated_collection(f"/repos/{repo}/issues?state=open&per_page=100")
                summary = summarize_implementation_issues(issues)
                row.update(summary)
            except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as error:
                detail = f"issue read failed: {error}"
                row["error"] = f"{row['error']}; {detail}" if row["error"] else detail
                if _systemic_api_failure(error):
                    global_error = row["error"]
        if row["error"]:
            row["status"] = "ERROR"
        elif row["missing"] or row["metadata_mismatch"]:
            row["status"] = "FAIL"
        else:
            row["status"] = "OK"
        rows.append(row)

    if any(row["status"] == "ERROR" for row in rows):
        return rows, 2
    if any(row["status"] == "FAIL" for row in rows):
        return rows, 1
    return rows, 0


def _render_health_row(row: dict[str, Any]) -> str:
    def value(name: str) -> object:
        current = row.get(name)
        return "UNKNOWN" if current is None else current

    missing = row.get("missing")
    mismatch = row.get("metadata_mismatch")
    missing_text = "UNKNOWN" if missing is None else ",".join(missing) or "none"
    mismatch_text = "UNKNOWN" if mismatch is None else ",".join(mismatch) or "none"
    line = (
        f"{row['repository']} implementation={value('implementation_count')} "
        f"priority_labelled={value('priority_labelled_count')} "
        f"unprioritized={value('unprioritized_count')} missing={missing_text} "
        f"metadata_mismatch={mismatch_text} status={row['status']}"
    )
    if row.get("excluded"):
        exclusions = ",".join(f"{key}:{count}" for key, count in row["excluded"].items())
        line += f" excluded={exclusions}"
    if row.get("error"):
        line += f" error={row['error']}"
    return line


def verify_bootstrap_settings(
    repo: str,
    *,
    bot: str = DEFAULT_BOT,
    keepalive_logins: str | None = None,
) -> dict[str, bool]:
    """Check whether all four bootstrap settings are in place for *repo*.

    Returns a mapping of setting id → bool (True = correctly configured).
    Each check is independent; a failure in one does not prevent the others.
    """
    results: dict[str, bool] = {}

    # 3.3.1 - workflow permissions
    try:
        proc = subprocess.run(
            _workflow_permissions_check_command(repo),
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(proc.stdout)
        results["workflow_permissions"] = (
            data.get("default_workflow_permissions") == "write"
            and data.get("can_approve_pull_request_reviews") is True
        )
    except subprocess.CalledProcessError:
        results["workflow_permissions"] = False

    # 3.3 - repo variables
    try:
        proc = subprocess.run(
            _variable_list_command(repo),
            check=True,
            capture_output=True,
            text=True,
        )
        variables = {v["name"]: v["value"] for v in json.loads(proc.stdout)}
        results["var_use_consolidated_workflows"] = (
            variables.get("USE_CONSOLIDATED_WORKFLOWS") == USE_CONSOLIDATED_WORKFLOWS_VALUE
        )
        expected_logins = keepalive_logins or _default_keepalive_logins(repo)
        results["var_allowed_keepalive_logins"] = (
            variables.get("ALLOWED_KEEPALIVE_LOGINS") == expected_logins
        )
    except subprocess.CalledProcessError:
        results["var_use_consolidated_workflows"] = False
        results["var_allowed_keepalive_logins"] = False

    # 3.1 - bot collaborator (the CLI endpoint call fails when not a collaborator)
    try:
        subprocess.run(
            _collaborator_check_command(repo, bot),
            check=True,
            capture_output=True,
            text=True,
        )
        results["bot_collaborator"] = True
    except subprocess.CalledProcessError:
        results["bot_collaborator"] = False

    return results


def build_bootstrap_plan(
    repo: str,
    *,
    keepalive_logins: str | None = None,
    bot: str = DEFAULT_BOT,
) -> list[dict[str, object]]:
    """Build the ordered list of bootstrap operations for ``repo``.

    Each operation is a dict with ``id``, ``description``, and ``command`` keys.
    Keeping this pure (no side effects) makes the plan unit-testable; execution
    is a thin wrapper in :func:`main`.
    """
    _split_repo(repo)
    logins = keepalive_logins or _default_keepalive_logins(repo)
    settings_plan = [
        {
            "id": "workflow_permissions",
            "description": "3.3.1 default_workflow_permissions=write, can_approve_pull_request_reviews=true",
            "command": _workflow_permissions_command(repo),
        },
        {
            "id": "var_use_consolidated_workflows",
            "description": "3.3 USE_CONSOLIDATED_WORKFLOWS variable",
            "command": _variable_command(
                repo, "USE_CONSOLIDATED_WORKFLOWS", USE_CONSOLIDATED_WORKFLOWS_VALUE
            ),
        },
        {
            "id": "var_allowed_keepalive_logins",
            "description": "3.3 ALLOWED_KEEPALIVE_LOGINS variable",
            "command": _variable_command(repo, "ALLOWED_KEEPALIVE_LOGINS", logins),
        },
        {
            "id": "bot_collaborator",
            "description": f"3.1 invite {bot} as push collaborator",
            "command": _collaborator_command(repo, bot),
        },
    ]
    return settings_plan + build_label_plan(repo)


def _format_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automate fresh-consumer bootstrap GitHub-settings toggles via gh CLI."
    )
    parser.add_argument(
        "--repo",
        help="Consumer repo in 'owner/name' form (e.g. stranske/Foo).",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_REGISTRY_MANIFEST,
        help="Registered-consumer workflow manifest used by --health-check.",
    )
    parser.add_argument(
        "--keepalive-logins",
        help="Comma-separated logins for ALLOWED_KEEPALIVE_LOGINS (default: repo owner).",
    )
    parser.add_argument(
        "--bot",
        default=DEFAULT_BOT,
        help=f"Service bot login to invite as collaborator (default: {DEFAULT_BOT}).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run the gh commands (default: dry run, print only).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read current workflow permissions and exit (no mutations).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Check all four bootstrap settings and report pass/fail (no mutations).",
    )
    parser.add_argument(
        "--labels-only",
        action="store_true",
        help="Limit dry-run or --execute to the three required priority labels.",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Audit every registered consumer's required labels and open issue counts.",
    )

    args = parser.parse_args()

    if sum([args.execute, args.check, args.verify, args.health_check]) > 1:
        raise SystemExit("Choose only one of --execute, --check, --verify, or --health-check.")
    if args.labels_only and (args.check or args.verify or args.health_check):
        raise SystemExit("--labels-only supports only dry-run or --execute mode.")
    if args.health_check:
        if args.repo:
            raise SystemExit("--health-check reads the registry; do not pass --repo.")
        if not args.manifest.is_file():
            raise SystemExit(f"Manifest not found: {args.manifest}")
        repos = extract_repos(args.manifest)
        rows, return_code = check_consumer_health(repos)
        for row in rows:
            print(_render_health_row(row))
        return return_code
    if not args.repo:
        raise SystemExit("--repo is required unless --health-check is used.")

    if args.check:
        cmd = _workflow_permissions_check_command(args.repo)
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout.strip())
        return 0

    if args.verify:
        status = verify_bootstrap_settings(
            args.repo,
            bot=args.bot,
            keepalive_logins=args.keepalive_logins,
        )
        all_ok = True
        for setting, ok in status.items():
            mark = "OK" if ok else "FAIL"
            print(f"[{mark}] {setting}")
            if not ok:
                all_ok = False
        return 0 if all_ok else 1

    if args.labels_only:
        plan = build_label_plan(args.repo)
    else:
        plan = build_bootstrap_plan(
            args.repo,
            keepalive_logins=args.keepalive_logins,
            bot=args.bot,
        )

    if args.execute:
        for op in plan:
            if str(op["id"]).startswith("label_"):
                continue
            cmd = op["command"]
            assert isinstance(cmd, list)
            print(f"# {op['description']}")
            # The command is an argv list (never a shell string), and every repo
            # component has already passed _split_repo's strict allowlist.
            # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
            subprocess.run(cmd, check=True)
        apply_priority_labels(args.repo)
        return 0

    for op in plan:
        cmd = op["command"]
        assert isinstance(cmd, list)
        print(f"# {op['description']}")
        print(_format_command(cmd))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
