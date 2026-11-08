#!/usr/bin/env python3
"""Resolve one agent run's pinned model and reasoning level from the shared model table.

The table (.github/agents/model-table.json) is the single source for hosted runners and for the
Orchestrator's local runs. Hosted runners call this at run time from .workflows-lib, so every
consumer repo uses the table at stranske/Workflows@workflows_ref without waiting for template sync.

Kind of work is chosen in this order: explicit --work-kind, a codex execution profile that names
a kind, the runner mode (autofix -> routine), then the table default.

Usage:
  agent_model_table.py resolve --agent claude --surface hosted [--work-kind K]
      [--execution-profile P] [--mode M] [--table PATH] [--github-output FILE]

Stdlib only: runners and the Orchestrator must not need PyYAML to read it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_TABLE = Path(__file__).resolve().parent.parent / ".github" / "agents" / "model-table.json"
SCHEMA = "agent-model-table/v1"


class TableError(ValueError):
    """The table is unreadable or cannot answer the request."""


def load_table(path: str | Path | None = None) -> dict[str, Any]:
    table_path = Path(path) if path else DEFAULT_TABLE
    try:
        table = json.loads(table_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TableError(f"cannot read model table {table_path}: {exc}") from exc
    if table.get("schema") != SCHEMA:
        raise TableError(
            f"model table {table_path} has schema {table.get('schema')!r}, need {SCHEMA}"
        )
    return table


def resolve_work_kind(
    table: dict[str, Any],
    *,
    work_kind: str | None = None,
    execution_profile: str | None = None,
    mode: str | None = None,
) -> tuple[str, str]:
    """Return (kind, how-it-was-chosen)."""
    kinds = table["work_kinds"]
    requested = (work_kind or "").strip()
    if requested:
        if requested not in kinds:
            raise TableError(f"unknown work kind {requested!r}; known: {', '.join(sorted(kinds))}")
        return requested, "work_kind input"
    profile = (execution_profile or "").strip()
    # codex-default is every codex caller's input default, so it cannot say what the caller meant.
    if profile and profile != "codex-default":
        kind = table.get("execution_profile_work_kinds", {}).get(profile)
        if kind:
            return kind, f"execution profile {profile}"
    mode_kind = table.get("mode_work_kinds", {}).get((mode or "").strip())
    if mode_kind:
        return mode_kind, f"runner mode {mode}"
    return table["default_work_kind"], "table default"


def resolve(
    table: dict[str, Any],
    agent: str,
    surface: str,
    *,
    work_kind: str | None = None,
    execution_profile: str | None = None,
    mode: str | None = None,
) -> dict[str, str]:
    provider = table["providers"].get(agent)
    if provider is None:
        raise TableError(f"agent {agent!r} is not in the model table")
    if surface not in provider["surfaces"]:
        raise TableError(f"agent {agent!r} does not run on surface {surface!r}")
    kind, chosen_by = resolve_work_kind(
        table, work_kind=work_kind, execution_profile=execution_profile, mode=mode
    )
    tier = table["work_kinds"][kind]["tier"]
    models = provider.get("surface_models", {}).get(surface) or provider["models"]
    model = models[tier]
    fallback = provider.get("surface_fallbacks", {}).get(surface) or provider["fallback"]
    effort = table["work_kinds"][kind]["effort"]
    spec = provider.get("effort") or {}
    effort_models = spec.get("models")
    if effort not in (spec.get("levels") or []) or (effort_models and model not in effort_models):
        effort = ""
    return {
        "agent": agent,
        "surface": surface,
        "work_kind": kind,
        "work_kind_source": chosen_by,
        "tier": tier,
        "model": model,
        "reasoning_effort": effort,
        "fallback_model": "" if fallback == model else fallback,
    }


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    res = sub.add_parser("resolve")
    res.add_argument("--agent", required=True)
    res.add_argument("--surface", default="hosted", choices=("hosted", "local"))
    res.add_argument("--work-kind", default="")
    res.add_argument("--execution-profile", default="")
    res.add_argument("--mode", default="")
    res.add_argument("--table", default="")
    res.add_argument("--github-output", default="", help="append key=value lines to this file")
    args = parser.parse_args(argv)
    try:
        result = resolve(
            load_table(args.table or None),
            args.agent,
            args.surface,
            work_kind=args.work_kind,
            execution_profile=args.execution_profile,
            mode=args.mode,
        )
    except TableError as exc:
        print(f"model table: {exc}", file=sys.stderr)
        return 2
    lines = [f"{key}={value}" for key, value in result.items()]
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
