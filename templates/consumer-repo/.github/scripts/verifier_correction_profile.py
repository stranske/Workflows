#!/usr/bin/env python3
"""Literal-only view of Core's existing reviewed role registry; never exec source."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping

SCHEMA = "closer-role-qualification/v1"
ROLE = "bounded_classification"
# Compatibility fingerprint of the reviewed reader semantics, excluding ONLY
# ROLE_QUALIFICATIONS' literal value. New reviewed records can be read; changed
# reader semantics stay UNKNOWN until this adapter is reviewed against them.
READER_SHA256 = "2deb2934814a97cc9f4066058ae4b1813240efcc500cb5e5bbd1ebe864ced9c8"
IDENTITY_TEXT = (
    "profile_id",
    "agent",
    "provider",
    "requested_model",
    "reasoning_effort",
    "permission_mode",
    "adapter_version",
    "prompt_version",
    "lifecycle_status",
)


def _shape(value):
    if isinstance(value, ast.AST):
        return [
            type(value).__name__,
            {
                key: _shape(item)
                for key, item in ast.iter_fields(value)
                if item is not None and item != []
            },
        ]
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return value


def _text(value):
    return isinstance(value, str) and bool(value) and value == value.strip()


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _identity(profile):
    if not isinstance(profile, Mapping) or any(not _text(profile.get(k)) for k in IDENTITY_TEXT):
        raise ValueError("profile identity is incomplete")
    if profile["agent"].casefold() == "aider" or profile["lifecycle_status"] != "active":
        raise ValueError("profile is not eligible/active")
    if profile["permission_mode"] not in {"read-only", "workspace-write"}:
        raise ValueError("profile permission mode is unsupported")
    result = {k: profile[k] for k in IDENTITY_TEXT}
    for key in ("transport_support", "capacity_pool_ids"):
        items = profile.get(key)
        if (
            not isinstance(items, list)
            or not items
            or any(not _text(v) for v in items)
            or len(set(items)) != len(items)
        ):
            raise ValueError("profile transport/capacity identity is incomplete")
        result[key] = sorted(items)
    if "offload" not in result["transport_support"]:
        raise ValueError("profile has no offload transport")
    explicit = profile.get("requires_explicit_selection", False)
    if type(explicit) is not bool:
        raise ValueError("profile explicit selection flag is invalid")
    result["requires_explicit_selection"] = explicit
    return result


def read_qualification(source, profile_id, now):
    def unknown(reason):
        return {"status": "owned_unknown", "reason": reason}

    try:
        if not isinstance(source, str) or len(source.encode()) > 1048576:
            return unknown("qualification source exceeds bound")
        if not _text(profile_id) or not _finite(now) or now < 0:
            return unknown("qualification observation identity/time invalid")
        tree = ast.parse(source)
        if sum(1 for _ in ast.walk(tree)) > 50000:
            return unknown("qualification source AST exceeds bound")
        bindings = []
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(target, ast.Name) and target.id == "ROLE_QUALIFICATIONS"
                    for target in targets
                ):
                    bindings.append(node)
        if len(bindings) != 1 or not isinstance(bindings[0].value, ast.Dict):
            return unknown("qualification registry is dynamic or ambiguous")
        # Duplicate literal keys can hide a revoked record or identity field.
        # Reject ambiguity before literal_eval applies Python's last-key wins.
        for node in ast.walk(bindings[0].value):
            if isinstance(node, ast.Dict):
                keys = [ast.literal_eval(key) for key in node.keys]
                if len(set(keys)) != len(keys):
                    return unknown("qualification registry literal has duplicate keys")
        records = ast.literal_eval(bindings[0].value)
        bindings[0].value = ast.Dict(keys=[], values=[])
        reader = hashlib.sha256(
            json.dumps(_shape(tree), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if reader != READER_SHA256:
            return unknown("reviewed Core qualification reader semantics unsupported")
        if not isinstance(records, dict) or len(records) > 128:
            return unknown("qualification registry exceeds bound")
        matches = []
        for key, record in records.items():
            if not _text(key) or not isinstance(record, dict):
                return unknown("qualification registry contains malformed record")
            bound = record.get("profile_identity")
            if (
                record.get("role") == ROLE
                and isinstance(bound, dict)
                and bound.get("profile_id") == profile_id
            ):
                matches.append((key, record))
        if len(matches) != 1:
            return unknown("role qualification is missing or ambiguous")
        key, record = matches[0]
        identity = _identity(record["profile_identity"])
        identity_sha = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        if (
            record.get("schema") != SCHEMA
            or record.get("status") != "qualified"
            or record.get("qualification_id") != key
        ):
            return unknown("role qualification schema/status/identity invalid or revoked")
        if (
            record.get("profile_identity") != identity
            or record.get("profile_identity_sha256") != identity_sha
            or record.get("transport") != "offload"
        ):
            return unknown("role qualification profile/transport differs")
        start, end = record.get("qualified_at"), record.get("expires_at")
        if not (_finite(start) and _finite(end) and 0 <= start <= now < end and start < end):
            return unknown("role qualification expired or original times invalid")
        refs, confinement = record.get("evidence_refs"), record.get("confinement")
        if (
            not isinstance(refs, list)
            or not refs
            or any(
                not isinstance(ref, dict)
                or not _text(ref.get("reference"))
                or not isinstance(ref.get("sha256"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", ref["sha256"])
                for ref in refs
            )
        ):
            return unknown("qualification evidence references unavailable")
        if not isinstance(confinement, dict) or not (
            confinement.get("data_only") is True
            and all(
                confinement.get(k) is False for k in ("tools", "mcp", "hooks", "project_context")
            )
            and isinstance(confinement.get("adapter_build_sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", confinement["adapter_build_sha256"])
        ):
            return unknown("bounded classification confinement evidence unavailable")
        return {
            "status": "qualified",
            "role": "closer_interpret",
            "record_role": ROLE,
            "profile_id": profile_id,
            "qualification_id": key,
            "record": record,
            "profile_identity_sha256": identity_sha,
            "runtime_execution": "not_attested",
        }
    except (ValueError, TypeError, SyntaxError, RecursionError, MemoryError, OverflowError) as exc:
        return unknown(f"literal qualification source unavailable: {type(exc).__name__}")


def main():
    raw = sys.stdin.buffer.read(2097153)
    if len(raw) > 2097152:
        result = {"status": "owned_unknown", "reason": "qualification input exceeds bound"}
    else:
        try:
            value = json.loads(raw)
            result = read_qualification(
                value.get("source"), value.get("profile_id"), value.get("now")
            )
        except (ValueError, AttributeError):
            result = {"status": "owned_unknown", "reason": "qualification input invalid"}
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
