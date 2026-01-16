#!/usr/bin/env python3
"""Emit step timing timestamps for auto-pilot workflows."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime
from pathlib import Path


def _utc_now_epoch_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_key(event: str, fmt: str) -> str:
    if fmt == "epoch-ms":
        return "AUTOPILOT_STEP_STARTED_AT_MS" if event == "start" else "AUTOPILOT_STEP_ENDED_AT_MS"
    return "AUTOPILOT_STEP_STARTED_AT" if event == "start" else "AUTOPILOT_STEP_ENDED_AT"


def timestamp_value(fmt: str) -> str:
    if fmt == "epoch-ms":
        return str(_utc_now_epoch_ms())
    return _utc_now_iso()


def append_env(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def env_path(var_name: str) -> Path:
    value = os.environ.get(var_name)
    if not value:
        raise ValueError(f"{var_name} is not set")
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Emit auto-pilot step timing values.")
    parser.add_argument("--event", choices=["start", "end"], required=True)
    parser.add_argument("--format", choices=["epoch-ms", "iso"], default="epoch-ms")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--env-path", help="Write KEY=VALUE to env file instead of stdout")
    destination.add_argument(
        "--output-path", help="Write KEY=VALUE to output file instead of stdout"
    )
    destination.add_argument(
        "--github-env",
        action="store_true",
        help="Write KEY=VALUE to $GITHUB_ENV instead of stdout",
    )
    destination.add_argument(
        "--github-output",
        action="store_true",
        help="Write KEY=VALUE to $GITHUB_OUTPUT instead of stdout",
    )
    parser.add_argument("--key", help="Override env var key (optional)")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    value = timestamp_value(args.format)
    key = args.key or default_key(args.event, args.format)
    if args.github_env:
        try:
            append_env(env_path("GITHUB_ENV"), key, value)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.github_output:
        try:
            append_env(env_path("GITHUB_OUTPUT"), key, value)
        except ValueError as exc:
            parser.error(str(exc))
    elif args.env_path:
        append_env(Path(args.env_path), key, value)
    elif args.output_path:
        append_env(Path(args.output_path), key, value)
    else:
        print(value)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    import sys

    raise SystemExit(main(sys.argv[1:]))
