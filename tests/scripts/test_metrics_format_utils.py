from scripts import metrics_format_utils


def test_format_percentage_respects_precision() -> None:
    assert metrics_format_utils.format_percentage(12.3456) == "12.3%"
    assert metrics_format_utils.format_percentage(12.3456, decimals=2) == "12.35%"
    assert metrics_format_utils.format_percentage(12.3456, decimals=0) == "12%"


def test_format_count_uses_pluralization() -> None:
    assert metrics_format_utils.format_count(1, "error") == "1 error"
    assert metrics_format_utils.format_count(0, "error") == "0 errors"
    assert metrics_format_utils.format_count(2, "error") == "2 errors"
    assert metrics_format_utils.format_count(2, "analysis", "analyses") == "2 analyses"


def test_summarize_patterns_orders_by_count() -> None:
    patterns = {"flaky": 1, "timeout": 3, "other": 2}
    assert metrics_format_utils.summarize_patterns(patterns) == [
        "timeout: 3",
        "other: 2",
        "flaky: 1",
    ]
    assert metrics_format_utils.summarize_patterns({}) == []


def test_summarize_patterns_keeps_insertion_order_on_ties() -> None:
    patterns = {"timeout": 2, "flaky": 2, "infra": 1}
    assert metrics_format_utils.summarize_patterns(patterns) == [
        "timeout: 2",
        "flaky: 2",
        "infra: 1",
    ]


def test_truncate_string_handles_limits() -> None:
    assert metrics_format_utils.truncate_string("short", max_length=10) == "short"
    assert metrics_format_utils.truncate_string("abcdefghij", max_length=10) == "abcdefghij"
    assert metrics_format_utils.truncate_string("abcdefghijk", max_length=10) == "abcdefg..."
    assert metrics_format_utils.truncate_string("longer", max_length=3) == "..."


def test_format_markdown_table_basic() -> None:
    table = metrics_format_utils.format_markdown_table(
        ["Metric", "Value"],
        [
            ["Total", 3],
            ["Success", "2/3"],
        ],
    )

    assert table == "\n".join(
        [
            "| Metric | Value |",
            "| --- | --- |",
            "| Total | 3 |",
            "| Success | 2/3 |",
        ]
    )


def test_format_markdown_table_alignment_and_escaping() -> None:
    table = metrics_format_utils.format_markdown_table(
        ["Name", "Notes"],
        [
            ["alpha|beta", "line1\nline2"],
        ],
        alignments=["left", "center"],
    )

    assert table == "\n".join(
        [
            "| Name | Notes |",
            "| --- | :---: |",
            r"| alpha\|beta | line1<br>line2 |",
        ]
    )


def test_format_markdown_table_rejects_bad_rows() -> None:
    try:
        metrics_format_utils.format_markdown_table(["A", "B"], [["only-one"]])
    except ValueError as exc:
        assert "Row length" in str(exc)
    else:
        raise AssertionError("Expected ValueError for mismatched row length")
