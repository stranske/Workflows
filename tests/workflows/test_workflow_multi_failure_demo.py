import pytest


def test_lint_failure():
    # Intentional lint error: missing whitespace after comma
    x = 1
    y = 2
    assert x == 1 and y == 2


def test_mypy_failure() -> None:
    # Intentional mypy error: assigning wrong type to variable
    x: int = "not an int"  # type: ignore[assignment]
    assert x == "not an int"


@pytest.mark.cosmetic
def test_cosmetic_failure():
    # Intentional cosmetic failure: formatting violation
    assert 1 == 1
