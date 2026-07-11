#!/usr/bin/env python3
"""Build a bounded handoff for Orchestrator's consumer-sync shadow rail."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.sync_manifest_compiler import PLAN_SCHEMA
except ImportError:
    from sync_manifest_compiler import PLAN_SCHEMA  # type: ignore[no-redef]


HANDOFF_SCHEMA = "workflows.consumer-sync-shadow-handoff/v1"
CAPABILITY_ID = "capability:reference-sync-hygiene-test-gate"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RUN_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/#@-]{0,255}$")
EFFECT_ALLOWLIST = ("create", "update", "remove", "skip", "no_change")


class ShadowHandoffError(ValueError):
    pass


def _stable_hash(namespace: str, value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(namespace.encode() + b"\0" + encoded).hexdigest()


def build_handoff(plan: Any, *, run_ref: str) -> dict[str, Any]:
    """Validate the compiler identity and emit a deterministic, non-authorizing handoff."""
    if not isinstance(plan, dict) or set(plan) != {
        "schema",
        "version",
        "plan_id",
        "manifest_sha256",
        "entries",
        "removals",
    }:
        raise ShadowHandoffError("invalid_consumer_sync_plan_fields")
    if plan.get("schema") != PLAN_SCHEMA or plan.get("version") != 1:
        raise ShadowHandoffError("unsupported_consumer_sync_plan_schema")
    if not SHA256_RE.fullmatch(str(plan.get("plan_id") or "")):
        raise ShadowHandoffError("invalid_consumer_sync_plan_id")
    if not SHA256_RE.fullmatch(str(plan.get("manifest_sha256") or "")):
        raise ShadowHandoffError("invalid_consumer_sync_manifest_hash")
    if not isinstance(plan.get("entries"), list) or not isinstance(plan.get("removals"), list):
        raise ShadowHandoffError("consumer_sync_plan_collections_not_arrays")
    if not RUN_REF_RE.fullmatch(run_ref):
        raise ShadowHandoffError("invalid_shadow_run_ref")
    if any(
        marker in run_ref.lower() for marker in ("token", "secret", "password", "api-key", "apikey")
    ):
        raise ShadowHandoffError("secret_like_shadow_run_ref")
    core = {
        "schema": HANDOFF_SCHEMA,
        "version": 1,
        "capability_id": CAPABILITY_ID,
        "plan_schema": PLAN_SCHEMA,
        "plan_id": plan["plan_id"],
        "manifest_sha256": plan["manifest_sha256"],
        "entry_count": len(plan["entries"]),
        "removal_count": len(plan["removals"]),
        "plan_filename": "consumer-sync-plan.json",
        "run_ref": run_ref,
        "supervision_mode": "shadow",
        "write_authority": False,
        "promotion_allowed": False,
        "effect_allowlist": list(EFFECT_ALLOWLIST),
        "kill_switch": "ORCH_REFERENCE_WORKFLOW_DISABLED=1",
        "consumer": "Orchestrator/consumer_sync_shadow.py",
    }
    return {**core, "handoff_id": _stable_hash("consumer-sync-shadow-handoff", core)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--run-ref", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        handoff = build_handoff(plan, run_ref=args.run_ref)
    except (OSError, json.JSONDecodeError, ShadowHandoffError) as exc:
        parser.error(str(exc))
    args.output.write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(handoff, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
