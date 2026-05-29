#!/usr/bin/env python3
"""Automate fresh-consumer bootstrap GitHub-settings toggles via gh CLI.

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
"""

from __future__ import annotations

import argparse
import shlex
import subprocess

DEFAULT_BOT = "stranske-automation-bot"
USE_CONSOLIDATED_WORKFLOWS_VALUE = "true"


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``owner/name`` into its parts, raising on malformed input."""
    parts = repo.strip().split("/")
    if len(parts) != 2 or not all(parts):
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
    return [
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


def _format_command(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automate fresh-consumer bootstrap GitHub-settings toggles via gh CLI."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Consumer repo in 'owner/name' form (e.g. stranske/Foo).",
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

    args = parser.parse_args()

    if args.execute and args.check:
        raise SystemExit("Choose either --execute or --check, not both.")

    if args.check:
        cmd = _workflow_permissions_check_command(args.repo)
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout.strip())
        return 0

    plan = build_bootstrap_plan(
        args.repo,
        keepalive_logins=args.keepalive_logins,
        bot=args.bot,
    )

    for op in plan:
        cmd = op["command"]
        assert isinstance(cmd, list)
        if args.execute:
            print(f"# {op['description']}")
            subprocess.run(cmd, check=True)
        else:
            print(f"# {op['description']}")
            print(_format_command(cmd))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
