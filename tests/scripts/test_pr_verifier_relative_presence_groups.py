"""Audit cache-local xdist pairs without another real-floor matrix."""

from collections import defaultdict
from itertools import product

import pytest

from tests.scripts import test_pr_verifier_delivery_destinations as delivery


def _rows():
    function = delivery.test_component_relative_presence_preserves_parent_actual_floor
    axes = [mark for mark in function.pytestmark if mark.name == "parametrize"]
    for values in product(*(mark.args[1] for mark in axes)):
        arguments = {}
        groups = []
        for mark, value in zip(axes, values, strict=True):
            names = mark.args[0].split(",")
            if hasattr(value, "values"):
                groups.extend(item.kwargs["name"] for item in value.marks)
                selected = value.values
            else:
                selected = value if len(names) > 1 else [value]
            arguments.update(zip(names, selected, strict=True))
        yield arguments, tuple(sorted(groups))


def test_relative_presence_groups_are_exactly_324_distinct_missing_status_pairs():
    pairs = defaultdict(list)
    for arguments, group in _rows():
        assert len(group) == 6
        assert all(name.startswith("rp-") for name in group)
        pairs[group].append(arguments)
    assert len(pairs) == 324
    for members in pairs.values():
        assert len(members) == 2
        assert {row["missing"] for row in members} == {"absent", "unavailable"}
        assert (
            len(
                {
                    tuple((key, value) for key, value in row.items() if key != "missing")
                    for row in members
                }
            )
            == 1
        )

    # These short group names belong only to this family, so other cases cannot
    # join its work units when the whole destination file runs under loadgroup.
    target = delivery.test_component_relative_presence_preserves_parent_actual_floor
    for function in vars(delivery).values():
        if function is target or not callable(function):
            continue
        for mark in getattr(function, "pytestmark", []):
            if mark.name == "xdist_group":
                assert not str(mark.kwargs.get("name", "")).startswith("rp-")
            if mark.name == "parametrize":
                for value in mark.args[1]:
                    for item in getattr(value, "marks", []):
                        if item.name == "xdist_group":
                            assert not str(item.kwargs.get("name", "")).startswith("rp-")


def test_relative_presence_keeps_every_classifier_and_floor_dispatch(monkeypatch):
    calls = []

    def capture(*args, **kwargs):
        assert not kwargs  # The caller must not opt out of any helper checks.
        calls.append(args)

    monkeypatch.setattr(
        delivery, "test_component_availability_preserves_bare_sibling_and_passive_actor", capture
    )
    for arguments, _ in _rows():
        delivery.test_component_relative_presence_preserves_parent_actual_floor(**arguments)
    assert len(calls) == len(set(calls)) == 648 * 4
    assert {row[8] for row in calls} == {
        " that may contain command output",
        " that must contain command output",
        " that must not contain command output",
        " that must contain command output if available",
    }


@pytest.mark.parametrize("missing", ["absent", "unavailable"])
def test_component_helper_executes_all_body_comment_floor_states(monkeypatch, missing):
    pending = []
    observed = []
    real_prompt_coverage = delivery.verifier.prompt_coverage
    real_floor = delivery.verifier._apply_coverage_floor

    def observe_prompt(context, diff):
        states = tuple(
            next(line for line in context.splitlines() if line.startswith(prefix))
            .removeprefix(prefix)
            .removesuffix("**")
            for prefix in ("- PR body: **", "- PR comments: **")
        )
        coverage = real_prompt_coverage(context, diff)
        pending.append((coverage, states))
        return coverage

    def observe_floor(result, coverage):
        prompt_coverage, states = pending.pop(0)
        assert coverage is prompt_coverage
        result = real_floor(result, coverage)
        observed.append((*states, result.verdict))
        return result

    monkeypatch.setattr(delivery.verifier, "prompt_coverage", observe_prompt)
    monkeypatch.setattr(delivery.verifier, "_apply_coverage_floor", observe_floor)
    delivery.test_component_availability_preserves_bare_sibling_and_passive_actor(
        "record",
        "active",
        "the PR body",
        "body",
        "a PR comment",
        "comments",
        "and",
        False,
        " that may contain command output",
        "must",
        True,
        missing,
    )
    assert not pending
    assert len(observed) == 4
    assert set(observed) == {
        (missing, missing, "UNVERIFIABLE_INPUT" if missing == "unavailable" else "CONCERNS"),
        ("present", missing, "UNVERIFIABLE_INPUT" if missing == "unavailable" else "CONCERNS"),
        (missing, "present", "PASS"),
        ("present", "present", "PASS"),
    }
