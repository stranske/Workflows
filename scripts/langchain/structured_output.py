from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


DEFAULT_REPAIR_PROMPT = """
The previous response did not match the required JSON schema.

Schema:
{schema_json}

Validation errors:
{validation_errors}

Original response:
{raw_response}

Return ONLY valid JSON that matches the schema with no surrounding text.
Do not wrap the JSON in markdown fences.
""".strip()

MIN_REPAIR_ATTEMPTS = 0
MAX_REPAIR_ATTEMPTS = 1


@dataclass(frozen=True)
class StructuredOutputResult(Generic[T]):
    payload: T | None
    raw_content: str | None
    error_stage: str | None
    error_detail: str | None
    repair_attempts_used: int = 0


def schema_json(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), ensure_ascii=True, indent=2)


def format_validation_errors(exc: ValidationError) -> str:
    return json.dumps(exc.errors(), ensure_ascii=True, indent=2)


def format_non_validation_error(exc: Exception) -> str:
    return json.dumps(
        [{"type": exc.__class__.__name__, "message": str(exc)}],
        ensure_ascii=True,
        indent=2,
    )


def build_repair_prompt(
    schema_json: str,
    validation_errors: str,
    raw_response: str,
    *,
    template: str = DEFAULT_REPAIR_PROMPT,
) -> str:
    return template.format(
        schema_json=schema_json,
        validation_errors=validation_errors,
        raw_response=raw_response,
    )


def build_repair_callback(
    client: Any, *, template: str = DEFAULT_REPAIR_PROMPT
) -> Callable[[str, str, str], str | None]:
    def _repair(schema_json: str, validation_errors: str, raw_response: str) -> str | None:
        try:
            repair_prompt = build_repair_prompt(
                schema_json=schema_json,
                validation_errors=validation_errors,
                raw_response=raw_response,
                template=template,
            )
            response = client.invoke(repair_prompt)
        except Exception:
            return None
        return getattr(response, "content", None) or str(response)

    return _repair


def clamp_repair_attempts(max_repair_attempts: int) -> int:
    return min(
        MAX_REPAIR_ATTEMPTS,
        max(MIN_REPAIR_ATTEMPTS, int(max_repair_attempts)),
    )


def _invoke_repair_loop(
    *,
    repair: Callable[[str, str, str], str | None] | None,
    attempts: int,
    model: type[T],
    error_detail: str,
    content: str,
) -> StructuredOutputResult[T]:
    if repair is None or attempts == 0:
        return StructuredOutputResult(
            payload=None,
            raw_content=None,
            error_stage="validation",
            error_detail=error_detail,
            repair_attempts_used=0,
        )
    repaired = repair(schema_json(model), error_detail, content)
    if not repaired:
        return StructuredOutputResult(
            payload=None,
            raw_content=None,
            error_stage="repair_unavailable",
            error_detail=error_detail,
            repair_attempts_used=1,
        )
    try:
        payload = model.model_validate_json(repaired)
        return StructuredOutputResult(
            payload=payload,
            raw_content=repaired,
            error_stage=None,
            error_detail=None,
            repair_attempts_used=1,
        )
    except ValidationError as repair_exc:
        repair_detail = format_validation_errors(repair_exc)
    except Exception as repair_exc:
        repair_detail = format_non_validation_error(repair_exc)
    else:
        repair_detail = None

    if repair_detail is not None:
        return StructuredOutputResult(
            payload=None,
            raw_content=None,
            error_stage="repair_validation",
            error_detail=repair_detail,
            repair_attempts_used=1,
        )

    return StructuredOutputResult(
        payload=None,
        raw_content=None,
        error_stage="validation",
        error_detail="Unknown validation error.",
        repair_attempts_used=0,
    )


def invoke_repair_loop(
    *,
    repair: Callable[[str, str, str], str | None] | None,
    attempts: int,
    model: type[T],
    error_detail: str,
    content: str,
) -> StructuredOutputResult[T]:
    return _invoke_repair_loop(
        repair=repair,
        attempts=attempts,
        model=model,
        error_detail=error_detail,
        content=content,
    )


def parse_structured_output(
    content: str,
    model: type[T],
    *,
    repair: Callable[[str, str, str], str | None] | None,
    max_repair_attempts: int = 1,
) -> StructuredOutputResult[T]:
    try:
        payload = model.model_validate_json(content)
        return StructuredOutputResult(
            payload=payload,
            raw_content=content,
            error_stage=None,
            error_detail=None,
            repair_attempts_used=0,
        )
    except ValidationError as exc:
        error_detail = format_validation_errors(exc)
    except Exception as exc:
        error_detail = format_non_validation_error(exc)
    else:
        error_detail = None

    if error_detail is not None:
        attempts = clamp_repair_attempts(max_repair_attempts)
        return invoke_repair_loop(
            repair=repair,
            attempts=attempts,
            model=model,
            error_detail=error_detail,
            content=content,
        )

    return StructuredOutputResult(
        payload=None,
        raw_content=None,
        error_stage="validation",
        error_detail="Unknown validation error.",
        repair_attempts_used=0,
    )
