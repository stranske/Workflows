#!/usr/bin/env python3
"""Drift check: hosted and local agent model tables must agree.

Counts every disagreement between the single source (.github/agents/model-table.json) and:
  1. the Orchestrator's copy (TABLE_JSON in src/model_table.py), leaf by leaf;
  2. active Codex execution_profiles in .github/agents/registry.yml (model, effort, fallback);
  3. registry.yml subscription_analysis.claude.model (the extract-kind Claude model);
  4. reusable-codex-run.yml input defaults (the implement kind);
  5. the hosted runners: each one must resolve its model through the table;
  6. the table itself (every tier pinned, every kind valid).

Prints `model tables agree: N mismatches` and exits 1 when N > 0. When the Orchestrator copy
cannot be read it prints `model tables: CANNOT COMPARE ...` and exits 2 -- an unreadable copy
is never reported as zero mismatches.

Usage:
  check_model_tables.py                          # Orchestrator copy from stranske/Orchestrator@main
  check_model_tables.py --orchestrator-table P   # a local copy: model_table.py or a .json file
  check_model_tables.py --orchestrator-ref REF   # another Orchestrator ref
  check_model_tables.py --skip-orchestrator      # in-repo checks only (CI); says so in the output
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent_model_table as amt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ORCHESTRATOR_COPY = "src/model_table.py"
BEGIN_MARK = '\nTABLE_JSON = r"""'
END_MARK = '\n"""  # END AGENT MODEL TABLE'
RAW_URL = "https://raw.githubusercontent.com/stranske/Orchestrator/{ref}/" + ORCHESTRATOR_COPY
HOSTED_RUNNERS = {
    "codex": ".github/workflows/reusable-codex-run.yml",
    "claude": ".github/workflows/reusable-claude-run.yml",
    "cursor": ".github/workflows/reusable-cursor-run.yml",
    "muse": ".github/workflows/reusable-muse-run.yml",
    "gemini": ".github/workflows/reusable-gemini-run.yml",
}


class CannotCompare(RuntimeError):
    pass


def _leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_leaves(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: value}


def compare_copies(source: dict[str, Any], copy: dict[str, Any]) -> list[str]:
    a, b = _leaves(source), _leaves(copy)
    problems = []
    for key in sorted(set(a) | set(b)):
        if a.get(key, "<absent>") != b.get(key, "<absent>"):
            problems.append(
                f"orchestrator copy: {key} = {b.get(key, '<absent>')!r}, source = {a.get(key, '<absent>')!r}"
            )
    return problems


def check_table(table: dict[str, Any]) -> list[str]:
    problems = []
    tiers = table.get("tiers") or []
    kinds = table.get("work_kinds") or {}
    for kind, spec in kinds.items():
        if spec.get("tier") not in tiers:
            problems.append(f"table: work kind {kind} names unknown tier {spec.get('tier')!r}")
    for mapping in ("mode_work_kinds", "execution_profile_work_kinds"):
        for key, kind in (table.get(mapping) or {}).items():
            if kind not in kinds:
                problems.append(f"table: {mapping}.{key} names unknown work kind {kind!r}")
    if table.get("default_work_kind") not in kinds:
        problems.append("table: default_work_kind is not a work kind")
    for agent, provider in (table.get("providers") or {}).items():
        for surface_models in [provider.get("models") or {}] + list(
            (provider.get("surface_models") or {}).values()
        ):
            for tier in tiers:
                if not str(surface_models.get(tier) or "").strip():
                    problems.append(f"table: {agent} has no pinned model for tier {tier}")
        if not str(provider.get("fallback") or "").strip():
            problems.append(f"table: {agent} has no fallback")
        if not set(provider.get("surfaces") or []) <= {"hosted", "local"} or not provider.get(
            "surfaces"
        ):
            problems.append(f"table: {agent} surfaces must be a non-empty subset of hosted/local")
    return problems


def check_registry(table: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    problems = []
    kinds = table.get("execution_profile_work_kinds") or {}
    for profile_id, profile in (registry.get("execution_profiles") or {}).items():
        if profile.get("agent") != "codex" or profile.get("lifecycle") != "active":
            continue
        kind = kinds.get(profile_id)
        if kind is None:
            problems.append(f"registry: active profile {profile_id} has no work kind in the table")
            continue
        want = amt.resolve(table, "codex", "hosted", work_kind=kind)
        # A profile names the provider's one fallback even when it equals the profile's model;
        # the runner drops a duplicate candidate, so that is agreement, not drift.
        for field, expected in (
            ("model", want["model"]),
            ("reasoning_effort", want["reasoning_effort"]),
            ("fallback_model", table["providers"]["codex"]["fallback"]),
        ):
            if str(profile.get(field) or "") != expected:
                problems.append(
                    f"registry: {profile_id}.{field} = {profile.get(field)!r}, table ({kind}) = {expected!r}"
                )
    claude = ((registry.get("subscription_analysis") or {}).get("claude") or {}).get("model")
    want = amt.resolve(table, "claude", "hosted", work_kind="extract")["model"]
    if claude != want:
        problems.append(
            f"registry: subscription_analysis.claude.model = {claude!r}, table (extract) = {want!r}"
        )
    return problems


def check_runners(table: dict[str, Any], root: Path, yaml_mod: Any) -> list[str]:
    problems = []
    for agent, rel in HOSTED_RUNNERS.items():
        if "hosted" not in table["providers"].get(agent, {}).get("surfaces", []):
            continue
        text = (root / rel).read_text(encoding="utf-8")
        if "agent_model_table.py" not in text or f"--agent {agent}" not in text:
            problems.append(f"runner: {rel} does not resolve its model through the shared table")
    codex = yaml_mod.safe_load((root / HOSTED_RUNNERS["codex"]).read_text(encoding="utf-8"))
    on = codex.get("on", codex.get(True)) or {}
    inputs = on["workflow_call"]["inputs"]
    want = amt.resolve(table, "codex", "hosted", work_kind=table["default_work_kind"])
    for name, expected in (
        ("codex_model", want["model"]),
        ("codex_reasoning_effort", want["reasoning_effort"]),
        ("codex_fallback_models", want["fallback_model"]),
    ):
        if str(inputs[name].get("default") or "") != expected:
            problems.append(
                f"runner: reusable-codex-run.yml input {name} default = {inputs[name].get('default')!r}, table = {expected!r}"
            )
    if f"DEFAULT_CODEX_MODEL: {want['model']}\n" not in (root / HOSTED_RUNNERS["codex"]).read_text(
        encoding="utf-8"
    ):
        problems.append("runner: reusable-codex-run.yml DEFAULT_CODEX_MODEL differs from the table")
    return problems


def embedded_table_text(module_text: str) -> str:
    """The table text the Orchestrator module carries between its markers."""
    start = module_text.find(BEGIN_MARK)
    end = module_text.find(END_MARK, start + 1)
    if start < 0 or end < 0:
        raise CannotCompare("no embedded TABLE_JSON block")
    return module_text[start + len(BEGIN_MARK) : end + 1]


def _parse_copy(text: str, where: str) -> dict[str, Any]:
    if where.endswith(".py"):
        text = embedded_table_text(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CannotCompare(f"{where}: {exc}") from exc


def load_orchestrator_copy(path: str | None, ref: str) -> tuple[dict[str, Any], str]:
    if path:
        try:
            return _parse_copy(Path(path).read_text(encoding="utf-8"), path), path
        except OSError as exc:
            raise CannotCompare(f"{path}: {exc}") from exc
    url = RAW_URL.format(ref=ref)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - fixed https host
            return _parse_copy(response.read().decode("utf-8"), url), url
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CannotCompare(f"{url}: {exc}") from exc


def run(
    root: Path = ROOT,
    *,
    orchestrator_table: str | None = None,
    orchestrator_ref: str = "main",
    skip_orchestrator: bool = False,
) -> tuple[list[str], str]:
    import yaml

    table = amt.load_table(root / ".github" / "agents" / "model-table.json")
    registry = yaml.safe_load(
        (root / ".github" / "agents" / "registry.yml").read_text(encoding="utf-8")
    )
    problems = (
        check_table(table) + check_registry(table, registry) + check_runners(table, root, yaml)
    )
    compared = "orchestrator copy NOT compared (--skip-orchestrator)"
    if not skip_orchestrator:
        copy, where = load_orchestrator_copy(orchestrator_table, orchestrator_ref)
        problems += compare_copies(table, copy)
        compared = f"orchestrator copy compared: {where}"
    return problems, compared


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--orchestrator-table", default="")
    parser.add_argument("--orchestrator-ref", default="main")
    parser.add_argument("--skip-orchestrator", action="store_true")
    args = parser.parse_args(argv)
    try:
        problems, compared = run(
            orchestrator_table=args.orchestrator_table or None,
            orchestrator_ref=args.orchestrator_ref,
            skip_orchestrator=args.skip_orchestrator,
        )
    except CannotCompare as exc:
        print(f"model tables: CANNOT COMPARE (orchestrator copy unreadable: {exc})")
        return 2
    for problem in problems:
        print(f"MISMATCH {problem}")
    print(compared)
    print(f"model tables agree: {len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
