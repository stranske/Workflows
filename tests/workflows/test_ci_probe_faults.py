import pytest

from trend_analysis import _ci_probe_faults as probe


@pytest.mark.parametrize("a,b,expected", [(1, 2, 3), (-5, 7, 2), (0, 0, 0)])
def test_add_numbers(a, b, expected):
    """Ensure the simple addition helper returns the correct sum."""
    assert probe.add_numbers(a, b) == expected


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({}, "Hello World"),
        ({"name": "Codex"}, "Hello Codex"),
        ({"name": "Codex", "excited": True}, "Hello Codex!"),
    ],
)
def test_build_message_variants(kwargs, expected):
    """The greeting builder should respect optional parameters."""
    assert probe.build_message(**kwargs) == expected


def test_internal_helper_aggregates_and_uses_dependencies(monkeypatch):
    """The internal helper should sum values and invoke helper imports."""
    captured = {}

    def fake_safe_load(text):
        captured["yaml"] = text
        return {"numbers": [1, 2, 3]}

    def fake_sqrt(value):
        captured.setdefault("sqrt_args", []).append(value)
        return 42

    monkeypatch.setattr(probe.yaml, "safe_load", fake_safe_load)
    monkeypatch.setattr(probe.math, "sqrt", fake_sqrt)

    values = [10, 20, 30]
    assert probe._internal_helper(values) == 60
    assert captured["yaml"] == "numbers: [1,2,3]"
    assert captured["sqrt_args"] == [10]


def test_internal_helper_handles_empty_sequence(monkeypatch):
    """Empty iterables should not break the helper and still call
    dependencies."""
    calls = {}

    monkeypatch.setattr(
        probe.yaml, "safe_load", lambda text: (calls.__setitem__("yaml", text), text)[1]
    )
    monkeypatch.setattr(probe.math, "sqrt", lambda value: (calls.__setitem__("sqrt", value), 0)[1])

    assert probe._internal_helper([]) == 0
    assert calls["yaml"] == "numbers: [1,2,3]"
    assert calls["sqrt"] == 0
