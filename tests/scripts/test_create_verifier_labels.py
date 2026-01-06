from __future__ import annotations

import pytest

from scripts import create_verifier_labels as cvl


def test_filter_labels_defaults_to_all() -> None:
    labels = cvl._filter_labels(cvl.LABELS, [])
    assert [label["name"] for label in labels] == [label["name"] for label in cvl.LABELS]


def test_filter_labels_returns_subset_in_defined_order() -> None:
    labels = cvl._filter_labels(cvl.LABELS, ["verify:compare", "verify:checkbox"])
    assert [label["name"] for label in labels] == ["verify:checkbox", "verify:compare"]


def test_filter_labels_rejects_unknown_label() -> None:
    with pytest.raises(SystemExit, match="Unknown label name"):
        cvl._filter_labels(cvl.LABELS, ["verify:unknown"])
