import json

import pytest

from tools import test_failure_signature


def test_build_signature_hash_sorts_jobs() -> None:
    jobs = [
        {"name": "B", "step": "lint", "stack": "ValueError"},
        {"name": "A", "step": "test", "stack": "AssertionError"},
    ]
    expected = test_failure_signature.build_signature_hash(list(reversed(jobs)))
    assert test_failure_signature.build_signature_hash(jobs) == expected


def test_main_returns_zero_on_expected_match(capsys: pytest.CaptureFixture[str]) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "ValueError: boom"}]
    expected = test_failure_signature.build_signature_hash(jobs)

    exit_code = test_failure_signature.main(["--jobs", json.dumps(jobs), "--expected", expected])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert expected in captured.out


def test_main_returns_one_on_expected_mismatch(capsys: pytest.CaptureFixture[str]) -> None:
    jobs = [{"name": "Tests", "step": "pytest", "stack": "ValueError: boom"}]

    exit_code = test_failure_signature.main(
        ["--jobs", json.dumps(jobs), "--expected", "deadbeef0000"]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Hash mismatch" in captured.err


def test_main_returns_two_on_invalid_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = test_failure_signature.main(["--jobs", "{not-json"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Invalid --jobs JSON" in captured.err
