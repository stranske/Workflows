"""Parity test: canonical read_ndjson_file is wired into the migrated scripts.

The deliberate-break gate must FAIL when src/ndjson_parser.read_ndjson_file is
patched to return ([], []), proving that the scripts consume the canonical and
that this test exercises the real code path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ndjson_parser import read_ndjson_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOD_RECORD = {"pr_number": 42, "iteration": 3, "status": "success"}
_ANOTHER_RECORD = {"pr_number": 99, "repo": "stranske/Workflows"}

SAMPLE_NDJSON = "\n".join(
    [
        json.dumps(_GOOD_RECORD),
        json.dumps(_ANOTHER_RECORD),
        "{bad json here}",
        "",  # blank line — should be skipped silently
    ]
)


# ---------------------------------------------------------------------------
# Core canonical tests
# ---------------------------------------------------------------------------


def test_read_ndjson_file_parses_valid_records(tmp_path: Path) -> None:
    """read_ndjson_file returns the two valid records from a mixed-content file."""
    ndjson_file = tmp_path / "sample.ndjson"
    ndjson_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    records, errors = read_ndjson_file(ndjson_file)

    assert records == [_GOOD_RECORD, _ANOTHER_RECORD]


def test_read_ndjson_file_surfaces_malformed_line(tmp_path: Path) -> None:
    """read_ndjson_file surfaces the malformed line in the errors list."""
    ndjson_file = tmp_path / "sample.ndjson"
    ndjson_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    records, errors = read_ndjson_file(ndjson_file)

    assert len(errors) == 1
    assert "invalid JSON" in errors[0]


def test_read_ndjson_file_missing_file_returns_error(tmp_path: Path) -> None:
    """read_ndjson_file returns empty records and an OSError string for missing files."""
    missing = tmp_path / "does_not_exist.ndjson"

    records, errors = read_ndjson_file(missing)

    assert records == []
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# Parity tests: migrated scripts consume the canonical
# ---------------------------------------------------------------------------


def test_aggregate_repo_metrics_consumes_canonical(tmp_path: Path) -> None:
    """aggregate_repo_metrics.read_repo_metrics reads via canonical (not local copy)."""
    from scripts.aggregate_repo_metrics import read_repo_metrics

    ndjson_file = tmp_path / "repo_metrics.ndjson"
    ndjson_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    tagged_records, error_count = read_repo_metrics(ndjson_file, repo="stranske/Workflows")

    # Two valid records — each should be tagged with the repo name
    assert len(tagged_records) == 2
    for record in tagged_records:
        assert record["repo"] == "stranske/Workflows"
    # One malformed line must have been tracked
    assert error_count == 1


def test_aggregate_repo_metrics_returns_correct_record_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that patching read_ndjson_file propagates through to aggregate_repo_metrics.

    This is the deliberate-break target: if read_ndjson_file is stubbed to
    return ([], []) then tagged_records must be empty — proving the path is live.
    """
    from scripts import aggregate_repo_metrics

    ndjson_file = tmp_path / "repo_metrics.ndjson"
    ndjson_file.write_text(SAMPLE_NDJSON, encoding="utf-8")

    # Patch the canonical as imported by aggregate_repo_metrics (via src.ndjson_parser)
    import src.ndjson_parser as ndjson_mod

    monkeypatch.setattr(ndjson_mod, "read_ndjson_file", lambda path: ([], []))

    tagged_records, error_count = aggregate_repo_metrics.read_repo_metrics(
        ndjson_file, repo="stranske/Workflows"
    )

    # Restore happens automatically via monkeypatch fixture teardown
    assert tagged_records == [], "Patched canonical must propagate — no records returned"
    assert error_count == 0

    monkeypatch.undo()

    # After undo, real records come back
    tagged_records_real, _ = aggregate_repo_metrics.read_repo_metrics(
        ndjson_file, repo="stranske/Workflows"
    )
    assert len(tagged_records_real) == 2
