"""Audit the retained grammar cases without running another Cartesian suite."""

import json
from itertools import combinations, product
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
        sum(entry["retained_count"] for entry in entries) == 27195
    )  # Classifier corpus plus representative coverage-floor witnesses (see verifier-grammar-matrices.md).
    matrices = json.loads(MATRICES.read_text(encoding="utf-8"))
    bounded = {row["function"]: row for row in matrices}
    assert len(bounded) == len(matrices) == 37
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
        elif entry.get("integration_floor_split"):
            assert entry["retained_count"] < entry["original_count"], name
            assert entry["original_dimensions"], name
            assert prod(dim["size"] for dim in entry["original_dimensions"]) == (
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


def test_integration_floor_split_preserves_distinct_outcomes_and_full_status_channels():
    """Verify integration_floor_split entries have one witness per outcome,
    cover all BODY_CLAUSE_CASES channel sets, and parametrize over
    status/channel as declared.
    """
    from tests.scripts.test_pr_verifier_delivery_destinations import BODY_CLAUSE_FLOOR_CASES

    entries = json.loads(INVENTORY.read_text(encoding="utf-8"))["functions"]
    split_entries = [entry for entry in entries if entry.get("integration_floor_split")]
    assert len(split_entries) == 1, "Expected exactly one integration_floor_split entry"
    entry = split_entries[0]
    assert entry["function"] == "test_body_clause_matrix_controls_real_coverage_floor"

    # Verify retained count matches: 6 outcomes × 3 statuses × 3 channels = 54
    assert entry["retained_count"] == 54
    assert entry["original_count"] == 963

    # Get the actual function and its parametrizations
    function = vars(delivery)[entry["function"]]
    marks = _parametrizations(function)
    assert (
        len(marks) == 3
    ), "Expected 3 parametrize decorators (criterion,expected), status, channel"

    # Check parameter names match the inventory (order may vary by decorator)
    all_param_names = set()
    for mark in marks:
        names = _parameter_names(mark)
        all_param_names.update(names)
    assert all_param_names == {"criterion", "expected", "status", "channel"}

    # Verify status and channel parameter values
    status_mark = next(m for m in marks if _parameter_names(m) == ["status"])
    channel_mark = next(m for m in marks if _parameter_names(m) == ["channel"])
    status_values = status_mark.args[1]
    channel_values = channel_mark.args[1]
    assert set(status_values) == {"present", "absent", "unavailable"}
    assert set(channel_values) == {"body", "comments", "artifacts"}

    # Verify criterion,expected values match BODY_CLAUSE_FLOOR_CASES
    ce_mark = next(m for m in marks if set(_parameter_names(m)) == {"criterion", "expected"})
    ce_values = ce_mark.args[1]
    # ce_values contains tuples of (criterion, expected_list)
    expected_ce_set = {
        (_freeze((criterion, tuple(sorted(expected_list)))))
        for criterion, expected_list in ce_values
    }
    actual_ce_set = {
        (_freeze((criterion, tuple(sorted(expected)))))
        for criterion, expected in BODY_CLAUSE_FLOOR_CASES
    }
    assert (
        expected_ce_set == actual_ce_set
    ), "Emitted criterion/expected pairs must match BODY_CLAUSE_FLOOR_CASES"

    # Verify we have all 6 distinct outcomes from BODY_CLAUSE_CASES
    assert len(BODY_CLAUSE_FLOOR_CASES) == 6
    floor_outcomes = {frozenset(expected) for _, expected in BODY_CLAUSE_FLOOR_CASES}
    assert len(floor_outcomes) == 6, "All 6 distinct outcomes must be unique"
    # Verify these are the expected channel sets
    assert floor_outcomes == {
        frozenset({"body"}),
        frozenset(),
        frozenset({"body", "comments"}),
        frozenset({"artifacts"}),
        frozenset({"comments"}),
        frozenset({"artifacts", "body", "comments"}),
    }


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
        projections = [semantic, *[[alias, *spine] for alias, spine in lexical.items()]]
        if matrix.get("pairwise"):
            projections.extend(combinations(dimensions, 2))
        for axes in projections:
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
