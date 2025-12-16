"""Intentional lint / style issues to exercise autofix pipeline.

This file deliberately violates formatting (spacing, line length), naming,
and ruff rules (unused imports, unused variables, ambiguous variable names)
so the reusable autofix workflow can demonstrate:
  * black reformatting
  * ruff --fix cleaning imports & variables
  * remaining_issues count after fixes

Safe to keep; assertions ensure test still passes post-fix.
"""

from math import sqrt as SQRT_ALIAS  # noqa: F401 (unused alias)


def test_autofix_spacing():
    x = 1 + 2
    y = 3 + 4
    z = (x + y) * 2
    # Intentional long expression to push wrapping behaviour for black
    result = x + y + z + 999 + 123 + 456 + 789 + 321 + 654 + 987 + 111 + 222 + 333
    assert result > 0


def test_unused_variable_chain():
    a = 10  # noqa: F841
    bb = 20  # noqa: F841
    _internal = 30  # noqa: F841
    meaning_of_life = 42
    assert meaning_of_life == 42


def test_shadow_builtin(list=list):  # noqa: A002 (shadow built-in intentionally)
    sample = list(range(3))
    assert sample == [0, 1, 2]


def test_mixed_quotes():
    single = "abc"
    double = "def"
    combined = f"{single}-{double}"
    assert combined == "abc-def"


def test_line_length_enforcement():  # This comment plus code below exceed default line length intentionally for black to reflow and shorten when formatted properly even though here it might be borderline but we ensure style corrections apply
    values = list(range(0, 15))
    assert len(values) == 15
