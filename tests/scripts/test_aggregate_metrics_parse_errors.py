"""How a metrics file that cannot be parsed is REPORTED.

`aggregate_agent_metrics.py` carries the highest churn in this repository (45 commits in the
window), and `_format_parse_error` — the function that turns a parse failure into the line an
operator reads — was unexercised across every one of its branches.

Each branch names a different fault with a different fix: malformed JSON on a line, a line that
parsed but is not an object, a legacy-fallback buffer that filled, and a file that could not be
read at all. Collapsed into one message, an operator debugging a metrics artifact cannot tell
which happened, and the aggregation reports fewer records either way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.aggregate_agent_metrics import _format_parse_error, read_metric_ndjson_files

# ---------------------------------------------------------------------------------------------
# The four messages. Each must name its own fault.
# ---------------------------------------------------------------------------------------------


def test_invalid_json_names_the_line_and_the_reason():
    msg = _format_parse_error(Path("m.ndjson"), 7, "invalid-json", "Expecting value")
    assert "m.ndjson:7" in msg
    assert "invalid JSON" in msg
    assert "Expecting value" in msg, "the parser's own reason is what makes this actionable"


def test_invalid_json_without_a_detail_still_names_the_line():
    msg = _format_parse_error(Path("m.ndjson"), 7, "invalid-json")
    assert "m.ndjson:7" in msg and "invalid JSON" in msg
    assert msg.rstrip().endswith("invalid JSON"), "no empty parenthetical when there is no detail"


def test_a_non_object_line_says_what_it_got_instead():
    """A bare list or string parses fine and is still unusable. Saying WHICH type arrived is the
    difference between a one-line fix and a hunt."""
    msg = _format_parse_error(Path("m.ndjson"), 3, "non-object-json", "list")
    assert "m.ndjson:3" in msg
    assert "expected object, got list" in msg


def test_the_legacy_fallback_buffer_limit_is_named_without_a_line():
    """A whole-file condition, so a line number would be a fiction."""
    msg = _format_parse_error(Path("m.ndjson"), None, "legacy-json-fallback-buffer-limit")
    assert msg == "m.ndjson: legacy-json-fallback-buffer-limit"


def test_an_unreadable_file_reports_the_os_reason_when_there_is_one():
    msg = _format_parse_error(Path("m.ndjson"), None, "unreadable-file", "Permission denied")
    assert msg == "m.ndjson: Permission denied"


def test_an_unreadable_file_with_no_reason_still_says_unreadable():
    """Silence here would leave a file that vanished from the aggregation with no explanation."""
    msg = _format_parse_error(Path("m.ndjson"), None, "unreadable-file")
    assert msg == "m.ndjson: unreadable file"


def test_the_four_reasons_produce_four_different_messages():
    """Asserted together, because the failure mode is COLLAPSE, not a wrong string.

    Four faults rendering identically is what stops an operator distinguishing them, and no
    single-branch test can catch that.
    """
    path = Path("m.ndjson")
    messages = {
        _format_parse_error(path, 1, "invalid-json", "boom"),
        _format_parse_error(path, 1, "non-object-json", "list"),
        _format_parse_error(path, None, "legacy-json-fallback-buffer-limit"),
        _format_parse_error(path, None, "unreadable-file", "nope"),
    }
    assert len(messages) == 4, messages


# ---------------------------------------------------------------------------------------------
# End to end: a real file on disk, read the way the aggregator reads it.
# ---------------------------------------------------------------------------------------------


def test_a_clean_ndjson_file_yields_its_records_and_no_errors(tmp_path):
    """The control. Without it, a reader that reported everything as broken would pass below."""
    f = tmp_path / "metrics.ndjson"
    f.write_text(
        json.dumps({"agent": "codex", "runs": 1}) + "\n" + json.dumps({"agent": "claude"}) + "\n",
        encoding="utf-8",
    )
    entries, errors = read_metric_ndjson_files([f])
    assert [e.get("agent") for e in entries] == ["codex", "claude"]
    assert errors == []


def test_a_file_that_does_not_exist_is_reported_not_skipped(tmp_path):
    """A missing artifact must not silently reduce the aggregate.

    Skipping it produces a smaller number that looks like a real measurement — the metrics
    equivalent of the absent-vs-zero confusion this whole area keeps hitting.
    """
    entries, errors = read_metric_ndjson_files([tmp_path / "absent.ndjson"])
    assert entries == []
    assert errors, "an unreadable file must produce an error, not silence"


def test_blank_lines_are_not_parse_errors(tmp_path):
    """Trailing newlines are ordinary. Reporting them would bury the real faults in noise."""
    f = tmp_path / "metrics.ndjson"
    f.write_text("\n" + json.dumps({"agent": "codex"}) + "\n\n\n", encoding="utf-8")
    entries, errors = read_metric_ndjson_files([f])
    assert len(entries) == 1
    assert errors == []


@pytest.mark.parametrize("bad", ["{not json", "[1, 2, 3]", '"a string"', "42"])
def test_a_malformed_or_non_object_line_is_reported(tmp_path, bad):
    """Both shapes are unusable to an aggregator keyed on object fields, and both are reported."""
    f = tmp_path / "metrics.ndjson"
    f.write_text(json.dumps({"agent": "codex"}) + "\n" + bad + "\n", encoding="utf-8")
    entries, errors = read_metric_ndjson_files([f])
    assert len(entries) == 1, "the good record must survive its neighbour"
    assert errors, f"{bad!r} should have been reported"
