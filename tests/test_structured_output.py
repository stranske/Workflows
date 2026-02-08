import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, Field, ValidationError

from scripts.langchain import structured_output
from scripts.langchain.structured_output import (
    DEFAULT_REPAIR_PROMPT,
    StructuredOutputResult,
    build_repair_callback,
    build_repair_prompt,
    format_non_validation_error,
    format_validation_errors,
    parse_structured_output,
    schema_json,
)


class ExampleModel(BaseModel):
    name: str
    age: int = Field(gt=0)


def _valid_payload() -> str:
    return json.dumps({"name": "Ada", "age": 30})


def _invalid_payload() -> str:
    return json.dumps({"name": "Ada", "age": -1})


def test_structured_output_result_dataclass_fields():
    result = StructuredOutputResult(
        payload=None,
        raw_content=None,
        error_stage="validation",
        error_detail="bad",
        repair_attempts_used=1,
    )
    assert result.error_stage == "validation"
    assert result.repair_attempts_used == 1


def test_schema_json_serializes_model_schema():
    schema = json.loads(schema_json(ExampleModel))
    assert "properties" in schema
    assert "name" in schema["properties"]
    assert "age" in schema["properties"]


def test_format_validation_errors_serializes_pydantic_errors():
    with pytest.raises(ValidationError) as exc_info:
        ExampleModel.model_validate_json(_invalid_payload())
    parsed = json.loads(format_validation_errors(exc_info.value))
    assert isinstance(parsed, list)
    assert parsed[0]["type"]


def test_format_non_validation_error_serializes_exception():
    parsed = json.loads(format_non_validation_error(ValueError("boom")))
    assert parsed == [{"type": "ValueError", "message": "boom"}]


def test_build_repair_prompt_uses_template():
    prompt = build_repair_prompt(
        "schema",
        "errors",
        "raw",
        template="schema:{schema_json} errors:{validation_errors} raw:{raw_response}",
    )
    assert prompt == "schema:schema errors:errors raw:raw"


def test_build_repair_callback_returns_content():
    class Response:
        content = _valid_payload()

        def __str__(self) -> str:
            return "fallback"

    class Client:
        def __init__(self) -> None:
            self.invocations: list[str] = []

        def invoke(self, prompt: str) -> Response:
            self.invocations.append(prompt)
            return Response()

    client = Client()
    callback = build_repair_callback(client, template=DEFAULT_REPAIR_PROMPT)
    repaired = callback("schema", "errors", "raw")
    assert repaired == _valid_payload()
    assert client.invocations


def test_build_repair_callback_returns_none_on_exception():
    class Client:
        def invoke(self, _prompt: str) -> Any:
            raise RuntimeError("boom")

    callback = build_repair_callback(Client())
    assert callback("schema", "errors", "raw") is None


def test_parse_structured_output_success():
    result = parse_structured_output(
        _valid_payload(),
        ExampleModel,
        repair=None,
        max_repair_attempts=1,
    )
    assert isinstance(result, StructuredOutputResult)
    assert result.payload is not None
    assert result.payload.name == "Ada"
    assert result.error_stage is None
    assert result.repair_attempts_used == 0


def test_parse_structured_output_validation_error_without_repair():
    result = parse_structured_output(
        _invalid_payload(),
        ExampleModel,
        repair=None,
        max_repair_attempts=1,
    )
    assert result.payload is None
    assert result.error_stage == "validation"
    assert result.repair_attempts_used == 0


def test_parse_structured_output_uses_repair_callback():
    def repair(_schema: str, _errors: str, _raw: str) -> str | None:
        return _valid_payload()

    result = parse_structured_output(
        _invalid_payload(),
        ExampleModel,
        repair=repair,
        max_repair_attempts=1,
    )
    assert result.payload is not None
    assert result.payload.age == 30
    assert result.error_stage is None
    assert result.repair_attempts_used == 1


def test_parse_structured_output_repair_unavailable():
    def repair(_schema: str, _errors: str, _raw: str) -> str | None:
        return None

    result = parse_structured_output(
        _invalid_payload(),
        ExampleModel,
        repair=repair,
        max_repair_attempts=1,
    )
    assert result.payload is None
    assert result.error_stage == "repair_unavailable"
    assert result.repair_attempts_used == 1


def test_parse_structured_output_repair_validation_error():
    def repair(_schema: str, _errors: str, _raw: str) -> str | None:
        return json.dumps({"name": "Ada"})

    result = parse_structured_output(
        _invalid_payload(),
        ExampleModel,
        repair=repair,
        max_repair_attempts=1,
    )
    assert result.payload is None
    assert result.error_stage == "repair_validation"
    assert result.repair_attempts_used == 1


@pytest.mark.parametrize(
    ("input_attempts", "expected_effective"),
    [(0, 0), (1, 1), (2, 1), (10, 1)],
)
def test_parse_structured_output_uses_effective_repair_attempts(
    input_attempts: int, expected_effective: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = {"effective": None}
    original_clamp = structured_output.clamp_repair_attempts

    def clamp_spy(value: int) -> int:
        effective = original_clamp(value)
        observed["effective"] = effective
        return effective

    monkeypatch.setattr(structured_output, "clamp_repair_attempts", clamp_spy)
    repair_spy = MagicMock(return_value=None)

    result = parse_structured_output(
        _invalid_payload(),
        ExampleModel,
        repair=repair_spy,
        max_repair_attempts=input_attempts,
    )

    # Production rule: max_repair_attempts is clamped to [MIN_REPAIR_ATTEMPTS, MAX_REPAIR_ATTEMPTS].
    assert observed["effective"] == expected_effective
    assert repair_spy.call_count == expected_effective
    assert result.repair_attempts_used == expected_effective
    if expected_effective == 0:
        assert result.error_stage == "validation"
    else:
        assert result.error_stage == "repair_unavailable"
