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


def test_parse_repos_from_workflow_reads_block(tmp_path) -> None:
    workflow = tmp_path / "workflow.yml"
    workflow.write_text(
        "\n".join(
            [
                "name: Example",
                "env:",
                "  REGISTERED_CONSUMER_REPOS: |",
                "    stranske/Foo",
                "    # comment",
                "    stranske/Bar",
                "",
                "jobs:",
                "  noop:",
                "    runs-on: ubuntu-latest",
            ]
        ),
        encoding="utf-8",
    )

    assert cvl._parse_repos_from_workflow(workflow) == ["stranske/Foo", "stranske/Bar"]


def test_normalize_repo_list_dedupes_in_order() -> None:
    repos = ["a", "b", "a", "c", "b"]
    assert cvl._normalize_repo_list(repos) == ["a", "b", "c"]


def test_validate_repo_count_mismatch_raises() -> None:
    with pytest.raises(SystemExit, match="Expected 2 repos"):
        cvl._validate_repo_count(["one"], 2)
