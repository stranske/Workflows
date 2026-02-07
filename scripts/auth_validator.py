from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from scripts import api_client


@dataclass(frozen=True)
class AuthValidationResult:
    valid: bool
    skipped: bool
    error: str | None
    message: str | None
    scopes: frozenset[str] | None
    allowed_scopes: frozenset[str] | None
    extra_scopes: tuple[str, ...]
    missing_fields: tuple[str, ...]


def _normalize_scopes(value: Any) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, (set, frozenset, list, tuple)):
        return frozenset(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return frozenset(part.strip() for part in value.split(",") if part.strip())
    return None


def _build_result(
    *,
    valid: bool,
    skipped: bool,
    error: str | None,
    message: str | None,
    scopes: frozenset[str] | None,
    allowed_scopes: frozenset[str] | None,
    extra_scopes: Iterable[str] = (),
    missing_fields: Iterable[str] = (),
) -> AuthValidationResult:
    return AuthValidationResult(
        valid=valid,
        skipped=skipped,
        error=error,
        message=message,
        scopes=scopes,
        allowed_scopes=allowed_scopes,
        extra_scopes=tuple(extra_scopes),
        missing_fields=tuple(missing_fields),
    )


def validate_auth_payload(payload: dict[str, Any] | None) -> AuthValidationResult:
    if payload is None:
        return _build_result(
            valid=False,
            skipped=False,
            error="missing_payload",
            message="Missing authentication payload.",
            scopes=None,
            allowed_scopes=None,
            missing_fields=("payload",),
        )
    if not isinstance(payload, dict):
        return _build_result(
            valid=False,
            skipped=False,
            error="invalid_payload",
            message="Authentication payload must be a mapping.",
            scopes=None,
            allowed_scopes=None,
            missing_fields=("payload",),
        )

    missing_fields: list[str] = []
    if "scopes" not in payload:
        missing_fields.append("scopes")
    if "allowed_scopes" not in payload:
        missing_fields.append("allowed_scopes")
    if missing_fields:
        return _build_result(
            valid=False,
            skipped=False,
            error="missing_fields",
            message=f"Authentication payload missing fields: {', '.join(missing_fields)}.",
            scopes=None,
            allowed_scopes=None,
            missing_fields=missing_fields,
        )

    scopes = _normalize_scopes(payload.get("scopes"))
    allowed_scopes = _normalize_scopes(payload.get("allowed_scopes"))

    if scopes is None:
        return _build_result(
            valid=True,
            skipped=True,
            error="unknown_scopes",
            message="Unable to determine token scopes; skipping scope check.",
            scopes=None,
            allowed_scopes=allowed_scopes,
        )
    if allowed_scopes is None:
        return _build_result(
            valid=True,
            skipped=True,
            error="missing_allowed_scopes",
            message="No allowed scopes configured; skipping scope check.",
            scopes=scopes,
            allowed_scopes=None,
        )

    extra_scopes = sorted(scopes - allowed_scopes)
    if extra_scopes:
        extras = ", ".join(extra_scopes)
        allowed = ", ".join(sorted(allowed_scopes))
        return _build_result(
            valid=False,
            skipped=False,
            error="extra_scopes",
            message=(f"Token scopes exceed allowed scopes. Extras: {extras}. Allowed: {allowed}."),
            scopes=scopes,
            allowed_scopes=allowed_scopes,
            extra_scopes=extra_scopes,
        )

    return _build_result(
        valid=True,
        skipped=False,
        error=None,
        message=None,
        scopes=scopes,
        allowed_scopes=allowed_scopes,
    )


def validate_token_scopes(
    token: str,
    allowed_scopes: set[str],
    *,
    retry_attempts: int | None = None,
    retry_backoff: float | None = None,
) -> AuthValidationResult:
    scopes = api_client.fetch_oauth_scopes(
        token,
        retry_attempts=retry_attempts,
        retry_backoff=retry_backoff,
    )
    payload = {"scopes": scopes, "allowed_scopes": allowed_scopes}
    return validate_auth_payload(payload)
