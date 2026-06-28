import json
import re

import pytest
from tools import test_failure_signature

HASH_PATTERN = re.compile(r"^[0-9a-f]{12}$")


def assert_hash_shape(signature_hash: str) -> None:
    assert HASH_PATTERN.fullmatch(signature_hash)


def test_build_signature_hash_sorts_jobs_and_matches_known_composition() -> None:
    jobs = [
        {"name": "B", "step": "lint", "stack": "ValueError"},
        {"name": "A", "step": "test", "stack": "AssertionError"},
    ]

    signature_hash = test_failure_signature.build_signature_hash(jobs)

    assert signature_hash == test_failure_signature.build_signature_hash(list(reversed(jobs)))
    assert signature_hash == "ceaab8e8004a"
    assert_hash_shape(signature_hash)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Unit tests"),
        ("step", "tox"),
        ("stack", "AssertionError: changed"),
    ],
)
def test_build_signature_hash_is_sensitive_to_name_step_and_stack(
    field: str,
    value: str,
) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "ValueError: boom"}]
    changed_jobs = [dict(jobs[0], **{field: value})]

    original_hash = test_failure_signature.build_signature_hash(jobs)
    changed_hash = test_failure_signature.build_signature_hash(changed_jobs)

    assert_hash_shape(original_hash)
    assert_hash_shape(changed_hash)
    assert changed_hash != original_hash


def test_build_signature_hash_uses_documented_defaults_for_missing_fields() -> None:
    jobs = [
        {},
        {"name": "Tests"},
        {"step": "pytest"},
        {"stack": "ValueError: boom"},
    ]
    explicit_default_jobs = [
        {"name": "?", "step": "no-step", "stack": "no-stack"},
        {"name": "Tests", "step": "no-step", "stack": "no-stack"},
        {"name": "?", "step": "pytest", "stack": "no-stack"},
        {"name": "?", "step": "no-step", "stack": "ValueError: boom"},
    ]

    signature_hash = test_failure_signature.build_signature_hash(jobs)

    assert signature_hash == test_failure_signature.build_signature_hash(explicit_default_jobs)
    assert test_failure_signature.build_signature_hash([{}]) == "4020d866ca03"
    assert_hash_shape(signature_hash)


def test_main_returns_zero_and_prints_hash_on_expected_match(
    capsys: pytest.CaptureFixture[str],
) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "ValueError: boom"}]
    expected = "710948db01ff"

    exit_code = test_failure_signature.main(["--jobs", json.dumps(jobs), "--expected", expected])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == f"{expected}\n"
    assert captured.err == ""
    assert_hash_shape(expected)


def test_main_returns_one_on_expected_mismatch(capsys: pytest.CaptureFixture[str]) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "ValueError: boom"}]
    expected = "deadbeef0000"

    exit_code = test_failure_signature.main(["--jobs", json.dumps(jobs), "--expected", expected])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == "710948db01ff\n"
    assert f"Hash mismatch: expected {expected} got 710948db01ff" in captured.err


def test_main_returns_two_on_invalid_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = test_failure_signature.main(["--jobs", "{not-json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "Invalid --jobs JSON" in captured.err
