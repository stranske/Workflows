from __future__ import annotations

import pytest
from scripts.langchain import injection_guard


def test_check_prompt_injection_blocks_samples(injection_samples: list[dict[str, str]]) -> None:
    for sample in injection_samples:
        result = injection_guard.check_prompt_injection(sample["text"])
        assert result["blocked"] is True
        assert result["reason"]
        assert result["code"] == sample["code"]


def test_check_prompt_injection_handles_empty_inputs() -> None:
    assert injection_guard.check_prompt_injection("")["blocked"] is False
    assert injection_guard.check_prompt_injection("   ")["blocked"] is False
    assert injection_guard.check_prompt_injection(None)["blocked"] is False


def test_check_prompt_injection_coerces_non_string_inputs() -> None:
    assert injection_guard.check_prompt_injection(123)["blocked"] is False
    assert (
        injection_guard.check_prompt_injection(b"ignore previous instructions")["blocked"] is True
    )


def test_check_prompt_injection_handles_bad_str_objects() -> None:
    class BadStr:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    result = injection_guard.check_prompt_injection(BadStr())
    assert result["blocked"] is True
    assert result["code"] == "GUARD_ERROR"
    assert result["reason"].startswith("GUARD_ERROR:")


def test_check_prompt_injection_return_shape_for_allowed_input() -> None:
    result = injection_guard.check_prompt_injection("Plain issue description")

    assert set(result.keys()) == {"blocked", "reason", "code"}
    assert result["blocked"] is False
    assert result["reason"] == ""
    assert result["code"] is None


@pytest.mark.parametrize(
    ("reason", "expected_code"),
    [
        ("", "GUARD_ERROR"),
        ("INSTRUCTION_OVERRIDE missing delimiter", None),
        ("UNKNOWN_CODE: Something odd", None),
    ],
)
def test_check_prompt_injection_handles_malformed_detector_outputs(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
    expected_code: str | None,
) -> None:
    def fake_detect(_: str) -> tuple[bool, str]:
        return True, reason

    monkeypatch.setattr(injection_guard, "detect_prompt_injection", fake_detect)

    result = injection_guard.check_prompt_injection("trigger")
    assert result["blocked"] is True
    assert result["code"] == expected_code
    assert result["reason"]


@pytest.mark.parametrize(
    "bad_reason",
    [None, 123, 0, False],
)
def test_check_prompt_injection_handles_non_string_reason(
    monkeypatch: pytest.MonkeyPatch,
    bad_reason: object,
) -> None:
    """Detector returns non-string reason — should fall back to GUARD_ERROR."""

    def fake_detect(_: str) -> tuple[bool, object]:
        return True, bad_reason

    monkeypatch.setattr(injection_guard, "detect_prompt_injection", fake_detect)

    result = injection_guard.check_prompt_injection("trigger")
    assert result["blocked"] is True
    assert result["code"] == "GUARD_ERROR"
    assert "Invalid reason format" in result["reason"]


def test_check_prompt_injection_handles_known_good_reason_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_detect(_: str) -> tuple[bool, str]:
        return True, "ROLE_CONFUSION: demo"

    monkeypatch.setattr(injection_guard, "detect_prompt_injection", fake_detect)

    result = injection_guard.check_prompt_injection("trigger")
    assert result["blocked"] is True
    assert result["code"] == "ROLE_CONFUSION"
    assert result["reason"] == "ROLE_CONFUSION: demo"


@pytest.mark.parametrize(
    "known_code",
    [
        "INSTRUCTION_OVERRIDE",
        "SYSTEM_PROMPT_EXFILTRATION",
        "ROLE_CONFUSION",
        "ENCODED_INSTRUCTIONS",
        "TOOL_INJECTION",
    ],
)
def test_check_prompt_injection_recognises_all_known_reason_codes(
    monkeypatch: pytest.MonkeyPatch,
    known_code: str,
) -> None:
    """Every code listed in REASON_CODE_MESSAGES must be extracted correctly."""

    def fake_detect(_: str) -> tuple[bool, str]:
        return True, f"{known_code}: test detail"

    monkeypatch.setattr(injection_guard, "detect_prompt_injection", fake_detect)

    result = injection_guard.check_prompt_injection("trigger")
    assert result["blocked"] is True
    assert result["code"] == known_code
    assert result["reason"] == f"{known_code}: test detail"
