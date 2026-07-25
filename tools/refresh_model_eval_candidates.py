#!/usr/bin/env python3
"""Derive the verifier-pilot candidate set from the model registry.

Part of the self-feeding verifier-model promotion system (stranske/Workflows#2819),
move 1: candidates should never be hand-maintained (they drifted — a defunct
``claude-sonnet-4-6`` was listed while the current ``claude-opus-4-8`` was omitted).
Instead derive them from ``config/model_registry.json`` so a catalog change
automatically produces the right pilot candidates.

For each provider selected for the target profile:
  - incumbent  = that profile's reviewed selection for the provider
  - candidates = every OTHER current, non-blocked, same-provider catalogued model
                 whose positioning is not clearly non-verifier (``efficient``,
                 ``coding-worker-profile``).

``--write`` regenerates ``config/model_eval_candidates.json``; ``--check`` exits 1
if the committed file differs from the derived set (a drift gate).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "config" / "model_registry.json"
DEFAULT_CANDIDATES_PATH = _REPO_ROOT / "config" / "model_eval_candidates.json"
DEFAULT_PROFILE = "verifier-balanced"

# Positionings that are not verifier candidates (cost/speed tiers, worker profiles).
EXCLUDED_POSITIONINGS = frozenset({"efficient", "coding-worker-profile"})


def derive_candidates(
    registry: dict[str, Any], *, profile: str = DEFAULT_PROFILE
) -> dict[str, Any]:
    """Return the candidate set derived from the registry (pure function)."""
    incumbents: dict[str, str] = {
        str(sel.get("provider", "")): str(sel.get("model_id", ""))
        for sel in registry.get("selections", [])
        if sel.get("profile") == profile and sel.get("provider") and sel.get("model_id")
    }
    models = registry.get("models", [])

    candidates: list[dict[str, str]] = []
    for provider in sorted(incumbents):
        incumbent = incumbents[provider]
        candidates.append({"provider": provider, "model_id": incumbent, "role": "incumbent"})
        alternatives = sorted(
            str(m.get("model_id", ""))
            for m in models
            if str(m.get("provider", "")) == provider
            and str(m.get("model_id", "")) != incumbent
            and m.get("lifecycle") == "current"
            and not m.get("blocked", False)
            and str(m.get("positioning", "")) not in EXCLUDED_POSITIONINGS
        )
        for model_id in alternatives:
            candidates.append({"provider": provider, "model_id": model_id, "role": "candidate"})
    return {"candidates": candidates}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _serialize(candidates: dict[str, Any]) -> str:
    return json.dumps(candidates, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive verifier-pilot candidates from the registry."
    )
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="Regenerate the candidates file.")
    group.add_argument(
        "--check", action="store_true", help="Exit 1 if the committed file has drifted."
    )
    args = parser.parse_args(argv)

    try:
        registry = _load(args.registry)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read registry: {exc}", file=sys.stderr)
        return 2

    derived = derive_candidates(registry, profile=args.profile)
    if not derived["candidates"]:
        print(f"no selections for profile {args.profile!r}; nothing to derive", file=sys.stderr)
        return 2

    if args.write:
        args.candidates.write_text(_serialize(derived), encoding="utf-8")
        print(f"wrote {len(derived['candidates'])} candidate rows to {args.candidates}")
        return 0

    # --check
    try:
        committed = _load(args.candidates)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read candidates file: {exc}", file=sys.stderr)
        return 1
    if committed == derived:
        print("candidates are in sync with the registry.")
        return 0
    print(
        "candidates have DRIFTED from the registry. Run "
        "`python -m tools.refresh_model_eval_candidates --write` and commit.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
