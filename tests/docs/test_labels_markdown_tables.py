"""Validate Markdown label tables render with stable column counts."""

from pathlib import Path

LABELS_DOC = Path("docs/LABELS.md")


def _markdown_tables(lines: list[str]) -> list[list[str]]:
    tables: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            current.append(stripped)
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _cell_count(row: str) -> int:
    return len(row.strip().strip("|").split("|"))


def test_labels_markdown_tables_have_consistent_column_counts() -> None:
    lines = LABELS_DOC.read_text(encoding="utf-8").splitlines()
    tables = _markdown_tables(lines)

    assert tables, "Expected docs/LABELS.md to contain Markdown tables"

    for table in tables:
        expected = _cell_count(table[0])
        for row in table[1:]:
            assert _cell_count(row) == expected, row


def test_reviewed_label_rows_stay_three_column_rows() -> None:
    lines = LABELS_DOC.read_text(encoding="utf-8").splitlines()
    reviewed_rows = [
        line.strip()
        for line in lines
        if line.strip().startswith("|")
        and ("`workflow:source-needed`" in line or "`agents:apply-suggestions`" in line)
    ]

    assert reviewed_rows
    assert all(_cell_count(row) == 3 for row in reviewed_rows)
