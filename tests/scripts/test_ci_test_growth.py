"""Bounded controls for explicit unknowns in the growth-summary formatter."""

import copy
import json

import pytest
from scripts.ci_test_growth import format_growth_summary, junit_report


def _growth():
    return {
        "collection": None,
        "reported": None,
        "review_required": False,
        "budget": {"cases_per_function": 1000, "cases_per_file": 50000},
    }


def _summary_payload(summary):
    return json.loads(summary.split("```json\n", 1)[1].split("\n```", 1)[0])


@pytest.mark.parametrize(
    "collection, error",
    [
        (None, None),
        (None, "collection receipt unreadable"),
        (None, "collection receipt malformed or incomplete"),
        ({"total": 3, "complete": False}, None),
        ({"total": 3}, "collection receipt malformed or incomplete"),
        ({}, None),
        ({"total": True}, None),
        ({"total": -1}, None),
    ],
)
def test_unknown_collection_cannot_report_within_budget(collection, error):
    growth = _growth()
    growth["collection"] = collection
    if error:
        growth["collection_error"] = error
    original = copy.deepcopy(growth)

    summary = format_growth_summary(growth)

    assert "Selected collection cases: UNKNOWN" in summary
    assert "Collection budget review required: UNKNOWN" in summary
    assert _summary_payload(summary)["review_required"] is None
    assert growth == original
    if error:
        assert _summary_payload(summary)["collection_error"] == error


@pytest.mark.parametrize("total, review", [(0, False), (1000, False), (1001, True)])
def test_known_collection_preserves_zero_and_budget_signal(total, review):
    growth = _growth()
    growth["collection"] = {
        "total": total,
        "per_file": {"test_example.py": total},
        "largest_functions": [["test_example.py::test_matrix", total]],
    }
    growth["review_required"] = review

    summary = format_growth_summary(growth)

    assert f"Selected collection cases: {total}\n" in summary
    assert f"Collection budget review required: {review}\n" in summary
    assert _summary_payload(summary) == growth


@pytest.mark.parametrize("review", [None, 0, "False"])
def test_unknown_review_flag_stays_unknown_with_known_collection(review):
    growth = _growth()
    growth.update(collection={"total": 0}, review_required=review)

    summary = format_growth_summary(growth)

    assert "Selected collection cases: 0\n" in summary
    assert "Collection budget review required: UNKNOWN" in summary
    assert _summary_payload(summary)["review_required"] is None


@pytest.mark.parametrize("error", [None, "JUnit timing receipt unreadable or unsafe"])
def test_missing_or_unreadable_junit_timing_is_explicitly_unknown(error):
    growth = _growth()
    if error:
        growth["junit_error"] = error

    summary = format_growth_summary(growth)

    assert "JUnit reported cases: UNKNOWN" in summary
    assert "JUnit timing: UNKNOWN" in summary
    assert "summed worker time, not wall time" not in summary
    assert _summary_payload(summary)["reported"] is None
    if error:
        assert _summary_payload(summary)["junit_error"] == error


@pytest.mark.parametrize("duration", [None, "invalid", "0", "2"])
def test_parsed_junit_preserves_counts_independently_of_timing(tmp_path, duration):
    path = tmp_path / "junit.xml"
    time = f' time="{duration}"' if duration is not None else ""
    path.write_text(
        f'<testsuite><testcase classname="tests.example" name="test_matrix[1]"{time}/>'
        '<testcase classname="tests.example" name="test_matrix[2]" time="0">'
        '<failure message="real failure"/></testcase></testsuite>',
        encoding="utf-8",
    )
    growth = _growth()
    growth["reported"] = junit_report(path)
    original = copy.deepcopy(growth)

    summary = format_growth_summary(growth)

    assert "JUnit reported cases: 2\n" in summary
    if duration in ("0", "2"):
        assert "JUnit timing: KNOWN (summed worker time, not wall time)" in summary
        assert _summary_payload(summary)["reported"]["dominant_functions_worker_seconds"] == [
            ["tests.example::test_matrix", float(duration)]
        ]
    else:
        assert "JUnit timing: UNKNOWN" in summary
        assert _summary_payload(summary)["reported"]["dominant_functions_worker_seconds"] is None
    assert growth == original
