"""Only the fixture's own pytest configuration discovers these six cases."""

import pytest

from .sample import classify_size


@pytest.mark.parametrize(
    "value,expected", [(0, "empty"), (1, "small"), (9, "small"), (10, "large"), (100, "large")]
)
def test_classification_boundaries(value, expected):
    assert classify_size(value) == expected


def test_negative_counts_are_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        classify_size(-1)
