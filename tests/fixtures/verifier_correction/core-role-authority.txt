"""Evidence-bound Closer role eligibility, independent of effort and capacity.

Only reviewed records in this module qualify a production role. Capacity
reports, candidate metadata and worker output are not qualification authority.
The registry intentionally starts empty: fixture success does not qualify a
real model. Consumers must additionally check installed transport confinement
and acquire the existing shared provider pools before invoking a worker.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, TypeGuard

SCHEMA = "closer-role-qualification/v1"
BOUNDED_CLASSIFICATION = "bounded_classification"
STRONG_CRITERION_ADJUDICATION = "strong_criterion_adjudication"
CONSTRAINED_REPAIR = "constrained_repair"
TASK_ROLES = {
    "closer_interpret": BOUNDED_CLASSIFICATION,
    "closer_exception": STRONG_CRITERION_ADJUDICATION,
    "closer_repair": CONSTRAINED_REPAIR,
}
ROLES = frozenset(TASK_ROLES.values())
# Qualification of a repair worker is not permission to run any of these
# operations: the bound action plan must independently admit the exact fix.
MECHANICAL_OPERATIONS = frozenset({"format", "lint_fix", "docstring_fix"})
ROLE_QUALIFICATIONS: dict[str, dict[str, Any]] = {}
_LOGGER = logging.getLogger(__name__)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTITY_TEXT = (
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


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _finite(value: Any) -> TypeGuard[int | float]:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def profile_identity(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact semantic execution identity; missing fields never infer defaults."""
    if not isinstance(profile, Mapping):
        raise ValueError("profile identity must be an object")
    if any(not _text(profile.get(key)) for key in _IDENTITY_TEXT):
        raise ValueError("profile identity has missing or invalid fields")
    if profile["agent"].casefold() == "aider":
        raise ValueError("Aider is not an eligible Closer worker")
    if profile["lifecycle_status"] != "active":
        raise ValueError("profile lifecycle is not active")
    if profile["permission_mode"] not in {"read-only", "workspace-write"}:
        raise ValueError("profile permission mode is unsupported")
    result = {key: profile[key] for key in _IDENTITY_TEXT}
    for key in ("transport_support", "capacity_pool_ids"):
        values = profile.get(key)
        if (
            not isinstance(values, list)
            or not values
            or any(not _text(value) for value in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError(f"profile {key} is missing or invalid")
        result[key] = sorted(values)
    if "offload" not in result["transport_support"]:
        raise ValueError("profile has no supported offload transport")
    explicit = profile.get("requires_explicit_selection", False)
    if type(explicit) is not bool:
        raise ValueError("profile explicit selection flag is invalid")
    result["requires_explicit_selection"] = explicit
    return result


def identity_digest(profile: Mapping[str, Any]) -> str:
    value = profile_identity(profile)
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _evidence_problems(record: Mapping[str, Any], role: str) -> list[str]:
    problems = []
    refs = record.get("evidence_refs")
    if (
        not isinstance(refs, list)
        or not refs
        or any(
            not isinstance(ref, Mapping)
            or not _text(ref.get("reference"))
            or not isinstance(ref.get("sha256"), str)
            or not _SHA256.fullmatch(ref["sha256"])
            for ref in refs
        )
    ):
        problems.append("role qualification lacks bound evidence references")
    if role in {BOUNDED_CLASSIFICATION, STRONG_CRITERION_ADJUDICATION}:
        confinement = record.get("confinement")
        if not isinstance(confinement, Mapping) or not (
            confinement.get("data_only") is True
            and all(
                confinement.get(key) is False
                for key in ("tools", "mcp", "hooks", "project_context")
            )
            and isinstance(confinement.get("adapter_build_sha256"), str)
            and _SHA256.fullmatch(confinement["adapter_build_sha256"])
        ):
            problems.append("read-only role lacks explicit confinement evidence")
    if role == CONSTRAINED_REPAIR:
        repair = record.get("repair_capabilities")
        operations = repair.get("allowlisted_operations") if isinstance(repair, Mapping) else None
        if not isinstance(repair, Mapping) or not (
            repair.get("mechanical_only") is True
            and repair.get("substantive_edits") is False
            and all(
                repair.get(key) is True
                for key in (
                    "isolated_workspace",
                    "path_allowlist_enforced",
                    "operation_allowlist_enforced",
                    "test_required",
                )
            )
            and isinstance(operations, list)
            and bool(operations)
            and all(isinstance(operation, str) for operation in operations)
            and len(set(operations)) == len(operations)
            and set(operations) <= MECHANICAL_OPERATIONS
        ):
            problems.append("repair role lacks constrained mechanical capability evidence")
    if role == STRONG_CRITERION_ADJUDICATION and record.get("named_criterion_only") is not True:
        problems.append("adjudication role lacks named-criterion capability evidence")
    return problems


def qualification_problems(
    profile: Mapping[str, Any],
    role: str,
    *,
    now: float | None = None,
    records: Mapping[str, Any] | None = None,
) -> list[str]:
    """Check one exact reviewed record; ``records`` is an offline fixture seam.

    No file, provider, environment setting or capacity report is consulted.
    Expiry removes eligibility; it never supplies action or retry authority.
    """
    if not isinstance(role, str) or role not in ROLES:
        return ["unknown Closer role"]
    try:
        identity = profile_identity(profile)
        digest = identity_digest(profile)
    except ValueError as exc:
        return [str(exc)]
    current = time.time() if now is None else now
    if not _finite(current) or current < 0:
        return ["qualification observation time is invalid"]
    source = ROLE_QUALIFICATIONS if records is None else records
    if not isinstance(source, Mapping):
        return ["role qualification registry is invalid"]
    matches = []
    for key, record in source.items():
        if not _text(key) or not isinstance(record, Mapping):
            return ["role qualification registry contains a malformed record"]
        bound = record.get("profile_identity")
        if (
            record.get("role") == role
            and isinstance(bound, Mapping)
            and bound.get("profile_id") == identity["profile_id"]
        ):
            matches.append((key, record))
    if len(matches) != 1:
        return ["role qualification is missing or ambiguous"]
    key, record = matches[0]
    problems = []
    if record.get("schema") != SCHEMA or record.get("status") != "qualified":
        problems.append("role qualification schema or status is invalid")
    if record.get("qualification_id") != key:
        problems.append("role qualification identity differs")
    if (
        record.get("profile_identity") != identity
        or record.get("profile_identity_sha256") != digest
    ):
        problems.append("role qualification profile identity differs")
    if record.get("transport") != "offload":
        problems.append("role qualification transport differs")
    if role == CONSTRAINED_REPAIR and identity["permission_mode"] != "workspace-write":
        problems.append("repair profile lacks workspace-write permission")
    started, expires = record.get("qualified_at"), record.get("expires_at")
    if not (
        _finite(started)
        and _finite(expires)
        and 0 <= started <= current < expires
        and started < expires
    ):
        problems.append("role qualification is expired or has invalid original times")
    return problems + _evidence_problems(record, role)


def is_qualified(
    profile: Mapping[str, Any],
    role: str,
    *,
    now: float | None = None,
    records: Mapping[str, Any] | None = None,
) -> bool:
    return not qualification_problems(profile, role, now=now, records=records)


def qualified_record(
    profile: Mapping[str, Any],
    role: str,
    *,
    now: float | None = None,
    records: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return the same validated unique record for separate runtime build checks.

    The returned copy confers no transport or action authority. In particular,
    consumers must bind its confinement build digest to the installed adapter
    before launch rather than trusting a successful profile-level predicate.
    """
    source = ROLE_QUALIFICATIONS if records is None else records
    if not isinstance(source, Mapping):
        return None
    snapshot = deepcopy(dict(source))
    if qualification_problems(profile, role, now=now, records=snapshot):
        return None
    return next(
        dict(record)
        for record in snapshot.values()
        if record.get("role") == role
        and record.get("profile_identity", {}).get("profile_id") == profile["profile_id"]
    )


def is_runtime_qualified(
    profile: Mapping[str, Any],
    role: str,
    *,
    now: float | None = None,
    records: Mapping[str, Any] | None = None,
) -> bool:
    """Bind role evidence to the currently supported installed confinement build.

    This read-only check never invokes a provider or provisions an adapter.
    Missing role evidence avoids even the installed binary probe. Repair uses
    its separate mechanical capability contract; exact action-plan and workspace
    admission still belongs to the guarded action path.
    """
    record = qualified_record(profile, role, now=now, records=records)
    if record is None:
        return False
    import execution_profiles

    profile_id = profile["profile_id"]
    if profile_id in execution_profiles.PROFILE_RETIREMENTS:
        return False
    registered = execution_profiles.PROFILE_REGISTRY.get(profile_id)
    if not isinstance(registered, Mapping):
        return False
    try:
        if profile_identity(registered) != profile_identity(profile):
            return False
    except ValueError:
        return False
    if role == CONSTRAINED_REPAIR:
        return True
    # Only this adapter currently has an actual data-only confinement path.
    # A candidate or arbitrary build hash cannot enable another transport.
    if profile["agent"] != "claude":
        return False
    import adapters

    if record["confinement"]["adapter_build_sha256"] != getattr(
        adapters, "DATA_ONLY_CLAUDE_SHA256", None
    ):
        return False
    try:
        problem = adapters.data_only_problem("claude", "assess")
        if problem is not None:
            _LOGGER.debug(
                "Runtime confinement probe refused profile %s role %s: %s",
                profile_id,
                role,
                problem,
            )
            return False
        return True
    except (OSError, ValueError, RuntimeError) as exc:
        _LOGGER.debug(
            "Runtime confinement probe failed for profile %s role %s: %s", profile_id, role, exc
        )
        return False
