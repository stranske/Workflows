from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import ci_cosmetic_repair


def _payload(kind: str, **data: object) -> str:
    return f"{kind} {json.dumps(data)}"


def test_parse_failure_message_extracts_single_payload() -> None:
    instructions = ci_cosmetic_repair.parse_failure_message(
        "Assertion drifted: "
        + _payload(
            "COSMETIC_TOLERANCE",
            path="tests/fixtures/baseline.py",
            guard="float",
            key="EXPECTED_ALPHA",
            actual=1.23456,
            digits=3,
        ),
        source="tests.test_example::test_alpha",
    )

    assert len(instructions) == 1
    instruction = instructions[0]
    assert instruction.kind == "tolerance"
    assert instruction.path == Path("tests/fixtures/baseline.py")
    assert instruction.guard == "float"
    assert instruction.key == "EXPECTED_ALPHA"
    assert instruction.value == "1.235"
    assert instruction.source == "tests.test_example::test_alpha"


def test_parse_failure_message_extracts_multiple_payloads_in_order() -> None:
    message = " ".join(
        [
            _payload(
                "COSMETIC_TOLERANCE",
                path="tests/fixtures/one.py",
                guard="float",
                key="EXPECTED_ONE",
                value=2,
            ),
            "and",
            _payload(
                "COSMETIC_SNAPSHOT",
                path="tests/fixtures/snapshot.txt",
                guard="snapshot",
                key="baseline",
                replacement="updated\n# cosmetic-repair: snapshot baseline\n",
            ),
        ]
    )

    instructions = ci_cosmetic_repair.parse_failure_message(message, source="case")

    assert [instruction.kind for instruction in instructions] == ["tolerance", "snapshot"]
    assert [instruction.path for instruction in instructions] == [
        Path("tests/fixtures/one.py"),
        Path("tests/fixtures/snapshot.txt"),
    ]
    assert instructions[0].value == "2"
    assert instructions[1].value == "updated\n# cosmetic-repair: snapshot baseline\n"


def test_build_instruction_accepts_tolerance_and_snapshot_payloads() -> None:
    tolerance = ci_cosmetic_repair.build_instruction(
        "COSMETIC_TOLERANCE",
        {
            "path": "tests/fixtures/baseline.py",
            "guard": "float",
            "key": "EXPECTED",
            "actual": 10.125,
            "digits": 2,
        },
        source="tolerance-case",
    )
    snapshot = ci_cosmetic_repair.build_instruction(
        "COSMETIC_SNAPSHOT",
        {
            "path": "tests/fixtures/snapshot.txt",
            "guard": "snapshot",
            "key": "baseline",
            "replacement": "new snapshot",
        },
        source="snapshot-case",
    )

    assert tolerance.kind == "tolerance"
    assert tolerance.value == "10.12"
    assert tolerance.metadata["actual"] == 10.125
    assert snapshot.kind == "snapshot"
    assert snapshot.value == "new snapshot"
    assert snapshot.metadata["replacement"] == "new snapshot"


@pytest.mark.parametrize(
    ("kind", "payload", "message"),
    [
        ("COSMETIC_TOLERANCE", {"guard": "float", "value": 1}, "Missing target path"),
        ("COSMETIC_TOLERANCE", {"path": "tests/example.py", "value": 1}, "Missing guard"),
        (
            "COSMETIC_TOLERANCE",
            {"path": "tests/example.py", "guard": "float", "key": ["bad"], "value": 1},
            "Invalid key",
        ),
        (
            "COSMETIC_TOLERANCE",
            {"path": "tests/example.py", "guard": "float"},
            "Tolerance payload missing",
        ),
        (
            "COSMETIC_SNAPSHOT",
            {"path": "tests/snapshot.txt", "guard": "snapshot", "replacement": 7},
            "Snapshot repair requires",
        ),
    ],
)
def test_build_instruction_rejects_invalid_payloads(
    kind: str, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError, match=message):
        ci_cosmetic_repair.build_instruction(kind, payload, source="case")


def test_format_value_prefers_explicit_value_over_actual() -> None:
    assert ci_cosmetic_repair._format_value({"value": 4.2, "actual": 9.9}) == "4.2"


def test_format_value_uses_actual_fallback_and_numeric_formatting() -> None:
    assert ci_cosmetic_repair._format_value({"actual": 1.2345, "digits": 2}) == "1.23"
    assert ci_cosmetic_repair._format_value({"actual": "8.25", "format": ".1f"}) == "8.2"


def test_format_value_accepts_strings_and_rejects_unsupported_values() -> None:
    assert ci_cosmetic_repair._format_value({"value": "expected text"}) == "expected text"

    with pytest.raises(ci_cosmetic_repair.CosmeticRepairError, match="Unsupported value type"):
        ci_cosmetic_repair._format_value({"value": ["not", "supported"]})


def test_repair_instruction_absolute_path_resolves_relative_to_root(tmp_path: Path) -> None:
    instruction = ci_cosmetic_repair.RepairInstruction(
        kind="tolerance",
        path=Path("tests/fixtures/baseline.py"),
        guard="float",
        key="EXPECTED",
        value="1.23",
        metadata={},
        source="case",
    )

    assert instruction.absolute_path(tmp_path) == tmp_path / "tests/fixtures/baseline.py"


def test_collect_instructions_aggregates_records_without_running_pytest_or_git() -> None:
    records = [
        SimpleNamespace(
            id="tests.test_example::test_one",
            message=_payload(
                "COSMETIC_TOLERANCE",
                path="tests/fixtures/one.py",
                guard="float",
                key="EXPECTED_ONE",
                actual=1.2,
                digits=1,
            ),
        ),
        SimpleNamespace(
            id="tests.test_example::test_two",
            message=_payload(
                "COSMETIC_SNAPSHOT",
                path="tests/fixtures/two.txt",
                guard="snapshot",
                key="baseline",
                replacement="new baseline",
            ),
        ),
    ]

    instructions = ci_cosmetic_repair.collect_instructions(records)

    assert [instruction.source for instruction in instructions] == [
        "tests.test_example::test_one",
        "tests.test_example::test_two",
    ]
    assert [instruction.kind for instruction in instructions] == ["tolerance", "snapshot"]
    assert [instruction.value for instruction in instructions] == ["1.2", "new baseline"]
