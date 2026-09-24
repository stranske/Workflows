from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.integration_repo import DEFAULT_WORKFLOW_REF, render_integration_repo  # noqa: E402

DEFAULT_DISPOSABLE_ROOT = Path(".consumer-tests")
DEFAULT_DESTINATION = DEFAULT_DISPOSABLE_ROOT / "integration-repo"


class UnsafeDestinationError(ValueError):
    """Raised when --force targets a path outside the disposable test root."""


def _unsafe_destination_message(destination: Path, disposable_root: Path) -> str:
    return (
        f"Refusing --force for destination {destination}: expected a non-symlink "
        f"strict descendant of {disposable_root}."
    )


def ensure_destination(
    destination: Path,
    *,
    force: bool,
    disposable_root: Path = DEFAULT_DISPOSABLE_ROOT,
) -> None:
    resolved_destination: Path | None = None
    if force:
        if disposable_root.is_symlink() or destination.is_symlink():
            raise UnsafeDestinationError(_unsafe_destination_message(destination, disposable_root))
        try:
            resolved_root = disposable_root.resolve()
            resolved_destination = destination.resolve()
        except (OSError, RuntimeError) as exc:
            raise UnsafeDestinationError(
                _unsafe_destination_message(destination, disposable_root)
            ) from exc
        if resolved_root not in resolved_destination.parents:
            raise UnsafeDestinationError(_unsafe_destination_message(destination, disposable_root))
    if destination.exists():
        if force:
            assert resolved_destination is not None
            shutil.rmtree(resolved_destination)
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
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}" if existing else src_path
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
        help=(
            "Directory for the rendered integration repo or existing repo path; "
            "forced replacement is limited to .consumer-tests/."
        ),
    )
    parser.add_argument(
        "--workflow-ref",
        default=DEFAULT_WORKFLOW_REF,
        help="Reusable workflow ref to embed when rendering the integration repo.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete the destination directory tree before rendering, only when it "
            "is a non-symlink child of .consumer-tests/."
        ),
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
    except (FileExistsError, FileNotFoundError, UnsafeDestinationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return run_pytest(destination, args.pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
