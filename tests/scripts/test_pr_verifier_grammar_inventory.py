"""Audit the retained grammar cases without running another Cartesian suite."""

import json
from itertools import product
from math import prod
from pathlib import Path

from tests.scripts import test_pr_verifier_delivery_destinations as delivery

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/ci/verifier-grammar-inventory.json"
MATRICES = ROOT / "docs/ci/verifier-grammar-matrices.json"


def _parametrizations(function):
    return [mark for mark in getattr(function, "pytestmark", []) if mark.name == "parametrize"]


def _parameter_names(mark):
    names = mark.args[0]
    return [part.strip() for part in names.split(",")] if isinstance(names, str) else list(names)


def _freeze(value):
    # Some grouped dimensions (for example aspect triples) contain lists.
    return tuple(map(_freeze, value)) if isinstance(value, (list, tuple)) else value


def test_inventory_accounts_for_every_named_regression_and_case():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    entries = inventory["functions"]
    functions = {
        name: function
        for name, function in vars(delivery).items()
        if name.startswith("test_") and callable(function)
    }
    assert len({entry["function"] for entry in entries}) == len(entries)
    assert set(functions) == {entry["function"] for entry in entries}
    assert sum(entry["original_count"] for entry in entries) == 90550
    assert (
        sum(entry["retained_count"] for entry in entries) == 35064 + 49
    )  # Original retained corpus plus new section-boundary cases.
    matrices = json.loads(MATRICES.read_text(encoding="utf-8"))
    bounded = {row["function"]: row for row in matrices}
    assert len(bounded) == len(matrices) == 18
    for entry in entries:
        name = entry["function"]
        marks = _parametrizations(functions[name])
        assert prod(len(mark.args[1]) for mark in marks) == entry["retained_count"], name
        if name in bounded:
            matrix = bounded[name]
            assert matrix["source_base"] == inventory["source_base"], name
            assert matrix["original_count"] == entry["original_count"], name
            assert matrix["retained_count"] == entry["retained_count"], name
            assert prod(len(values) for values in matrix["dimensions"].values()) == (
                entry["original_count"]
            ), name
        elif entry["original_count"]:
            # Untouched matrices retain their full original Cartesian dimensions.
            dimensions = [
                {"names": _parameter_names(mark), "size": len(mark.args[1])} for mark in marks
            ]
            assert dimensions == entry["original_dimensions"], name
            assert entry["original_count"] == entry["retained_count"], name
    assert sum(entry["original_count"] > 0 for entry in entries) == 356


def test_emitted_cases_preserve_every_declared_semantic_and_lexical_projection():
    for matrix in json.loads(MATRICES.read_text(encoding="utf-8")):
        name = matrix["function"]
        dimensions = matrix["dimensions"]
        semantic = matrix["semantic"]
        lexical = matrix["lexical_spines"]
        assert set(semantic).isdisjoint(lexical), name
        assert set(semantic) | set(lexical) == set(dimensions), name
        marks = _parametrizations(getattr(delivery, name))
        assert len(marks) == 1, name
        mark = marks[0]
        names = [part.strip() for axis in dimensions for part in axis.split(",")]
        assert _parameter_names(mark) == names, name
        cases = {_freeze(case.values) for case in mark.args[1]}
        assert len(cases) == len(mark.args[1]) == matrix["retained_count"], name

        # Check witnesses against actual emitted rows. Only the bounded core and
        # declared spines are enumerated; no original Cartesian product is built.
        for axes in [semantic, *[[alias, *spine] for alias, spine in lexical.items()]]:
            assert set(axes) <= set(dimensions), name
            for selected in product(*(dimensions[axis] for axis in axes)):
                values = {axis: options[0] for axis, options in dimensions.items()}
                values.update(zip(axes, selected, strict=True))
                witness = tuple(
                    _freeze(value)
                    for axis, item in values.items()
                    for value in (item if "," in axis else [item])
                )
                assert witness in cases, (name, axes, selected)
