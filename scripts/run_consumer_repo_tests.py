from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.integration_repo import DEFAULT_WORKFLOW_REF, render_integration_repo

DEFAULT_DESTINATION = Path(".consumer-tests") / "integration-repo"


def ensure_destination(destination: Path, *, force: bool) -> None:
    if destination.exists():
        if force:
            shutil.rmtree(destination)
        elif any(destination.iterdir()):
            raise FileExistsError(
                f"Destination {destination} is not empty. Use --force to overwrite."
            )
    destination.mkdir(parents=True, exist_ok=True)


def build_pytest_command(pytest_args: Sequence[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", *pytest_args]


def build_pytest_env(destination: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(destination.resolve() / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing}" if existing else src_path
    )
    return env


def run_pytest(destination: Path, pytest_args: Sequence[str]) -> int:
    command = build_pytest_command(pytest_args)
    env = build_pytest_env(destination)
    result = subprocess.run(command, cwd=destination, env=env)
    return result.returncode


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run tests in a consumer repo (integration template by default)."
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help="Directory for the rendered integration repo or existing repo path.",
    )
    parser.add_argument(
        "--workflow-ref",
        default=DEFAULT_WORKFLOW_REF,
        help="Reusable workflow ref to embed when rendering the integration repo.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove existing destination contents before rendering.",
    )
    parser.add_argument(
        "--skip-render",
        action="store_true",
        help="Run tests in an existing consumer repo instead of rendering.",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Additional pytest args (pass after --pytest-args).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    destination = args.destination

    try:
        if args.skip_render:
            if not destination.exists():
                print(f"Destination not found: {destination}", file=sys.stderr)
                return 1
        else:
            ensure_destination(destination, force=args.force)
            render_integration_repo(destination, workflow_ref=args.workflow_ref)
    except (FileExistsError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return run_pytest(destination, args.pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
