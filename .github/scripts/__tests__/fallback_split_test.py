from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

# Add the scripts directory to the path so we can import the module
SCRIPT_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fallback_split  # noqa: F401,E402

SCRIPT = SCRIPT_DIR / "fallback_split.py"


def run_fallback(tmp_path: Path) -> SimpleNamespace:
    """Run fallback_split.py in a temporary directory and return results."""
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_cwd = os.getcwd()
    original_argv = sys.argv
    try:
        os.chdir(tmp_path)
        sys.argv = [str(SCRIPT)]
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(SCRIPT), run_name="__main__")
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(original_cwd)
        sys.argv = original_argv
    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


class TestFallbackSplitMissingInput:
    """Test behavior when input.txt is missing."""

    def test_missing_input_file_returns_1(self, tmp_path: Path) -> None:
        """main() returns 1 when input.txt is missing."""
        result = run_fallback(tmp_path)
        assert result.returncode == 1
        assert "missing" in result.stdout
        assert not (Path(tmp_path) / "topics.json").exists()


class TestFallbackSplitNoEnumerators:
    """Test behavior when no enumerators are found."""

    def test_no_enumerators_returns_2(self, tmp_path: Path) -> None:
        """main() returns 2 when no enumerators are found in input."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text("This is just plain text without any enumerators.")

        result = run_fallback(workdir)
        assert result.returncode == 2
        assert "no enumerators" in result.stdout
        assert not (workdir / "topics.json").exists()

    def test_empty_file_returns_2(self, tmp_path: Path) -> None:
        """main() returns 2 when input file is empty."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text("")

        result = run_fallback(workdir)
        assert result.returncode == 2
        assert "no enumerators" in result.stdout
        assert not (workdir / "topics.json").exists()


class TestFallbackSplitNumericEnumerators:
    """Test behavior with numeric enumerators."""

    def test_numeric_enumerators_generate_topics(self, tmp_path: Path) -> None:
        """Numeric enumerators generate topics.json with correct structure."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "1) First topic\n"
            "This is the content for the first topic.\n\n"
            "2) Second topic\n"
            "This is the content for the second topic.\n\n"
            "3. Third topic\n"
            "This is the content for the third topic.",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0
        assert (workdir / "topics.json").exists()

        # Parse and validate the generated JSON
        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        assert len(topics) == 3

        # Validate first topic structure - all required fields present
        topic1 = topics[0]
        assert "title" in topic1
        assert "labels" in topic1
        assert "sections" in topic1
        assert "extras" in topic1
        assert "enumerator" in topic1
        assert "continuity_break" in topic1
        assert "guid" in topic1
        assert "fallback" in topic1

        # Validate specific values for first topic
        assert topic1["title"] == "First topic"
        assert topic1["enumerator"] == "1)"
        assert topic1["fallback"] is True
        assert topic1["continuity_break"] is False
        assert topic1["labels"] == []
        assert topic1["sections"] == {}

        # Validate second topic
        topic2 = topics[1]
        assert topic2["title"] == "Second topic"
        assert topic2["enumerator"] == "2)"
        assert topic2["fallback"] is True

        # Validate third topic (with period enumerator)
        topic3 = topics[2]
        assert topic3["title"] == "Third topic"
        assert topic3["enumerator"] == "3."
        assert topic3["fallback"] is True

        assert "fallback_split: generated 3 topic(s)" in result.stdout

    def test_numeric_enumerators_with_different_delimiters(self, tmp_path: Path) -> None:
        """Test numeric enumerators with various delimiters (.) :-)."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "1. First topic\nContent here\n2) Second topic\nMore content\n"
            "3: Third topic\nEven more content\n4- Fourth topic\nFinal content",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        assert len(topics) == 4

        # Check enumerators are preserved
        assert topics[0]["enumerator"] == "1."
        assert topics[1]["enumerator"] == "2)"
        assert topics[2]["enumerator"] == "3:"
        assert topics[3]["enumerator"] == "4-"

    def test_numeric_enumerators_generate_stable_uuids(self, tmp_path: Path) -> None:
        """Test that the same input generates stable UUIDs."""
        workdir = Path(tmp_path)
        input_content = "1) Test topic\nContent here"
        (workdir / "input.txt").write_text(input_content, encoding="utf-8")

        # Run the function twice with the same input
        result1 = run_fallback(workdir)
        topics1 = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        guid1 = topics1[0]["guid"]

        # Run again with the same input
        result2 = run_fallback(workdir)
        topics2 = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        guid2 = topics2[0]["guid"]

        # UUIDs should be identical for the same input
        assert guid1 == guid2
        assert result1.returncode == result2.returncode == 0

        # Validate it's a valid UUID5 - the title "Test topic" should be normalized to "test topic"
        expected_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, "test topic"))
        assert guid1 == expected_guid


class TestFallbackSplitAlphaEnumerators:
    """Test behavior with alphabetic enumerators."""

    def test_alpha_enumerators_generate_topics(self, tmp_path: Path) -> None:
        """Alpha enumerators generate topics.json with correct structure."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "A) First alpha topic\nContent for A\n\n"
            "B. Second alpha topic\nContent for B\n\n"
            "C: Third alpha topic\nContent for C",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        assert len(topics) == 3

        # Validate first topic
        topic1 = topics[0]
        assert topic1["title"] == "First alpha topic"
        assert topic1["enumerator"] == "A)"
        assert topic1["fallback"] is True
        assert topic1["continuity_break"] is False

        # Validate second topic
        topic2 = topics[1]
        assert topic2["title"] == "Second alpha topic"
        assert topic2["enumerator"] == "B."

        # Validate third topic
        topic3 = topics[2]
        assert topic3["title"] == "Third alpha topic"
        assert topic3["enumerator"] == "C:"

    def test_mixed_numeric_alpha_enumerators(self, tmp_path: Path) -> None:
        """Test mixed numeric and alpha enumerators."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "1) Numeric topic\nContent\nA) Alpha topic\nMore content\n2. Another numeric\nFinal content",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        assert len(topics) == 3

        assert topics[0]["enumerator"] == "1)"
        assert topics[1]["enumerator"] == "A)"
        assert topics[2]["enumerator"] == "2."

    def test_alpha_enumerators_with_numbers(self, tmp_path: Path) -> None:
        """Test alpha enumerators that include numbers (like A1, B2)."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "A1) Topic with number\nContent\nB2. Another topic with number\nMore content",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
        assert len(topics) == 2

        assert topics[0]["enumerator"] == "A1)"
        assert topics[1]["enumerator"] == "B2."


class TestFallbackSplitExtrasAndContent:
    """Test that extras field contains the correct content."""

    def test_extras_contains_segment_content(self, tmp_path: Path) -> None:
        """Test that extras field contains the full segment content."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(
            "1) First topic\nLine 1\nLine 2\nLine 3\n\n2) Second topic\nAnother line",
            encoding="utf-8",
        )

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))

        # First topic extras should contain the full segment
        assert "Line 1" in topics[0]["extras"]
        assert "Line 2" in topics[0]["extras"]
        assert "Line 3" in topics[0]["extras"]

        # Second topic extras should contain its segment
        assert "Another line" in topics[1]["extras"]

    def test_long_title_truncation(self, tmp_path: Path) -> None:
        """Test that long titles are truncated to 120 characters."""
        long_title = "A" * 150  # 150 characters
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text(f"1) {long_title}\nContent", encoding="utf-8")

        result = run_fallback(workdir)
        assert result.returncode == 0

        topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))

        # Title should be truncated to 120 characters
        assert len(topics[0]["title"]) <= 120
        assert topics[0]["title"] == "A" * 120
        assert topics[0]["enumerator"] == "1)"


class TestFallbackSplitExitCodeCompatibility:
    """Test that existing exit codes remain compatible."""

    def test_success_returns_0(self, tmp_path: Path) -> None:
        """Successful execution returns 0."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text("1) Test topic\nContent", encoding="utf-8")

        result = run_fallback(workdir)
        assert result.returncode == 0
        assert (workdir / "topics.json").exists()

    def test_missing_input_returns_1(self, tmp_path: Path) -> None:
        """Missing input returns 1 (existing behavior)."""
        result = run_fallback(tmp_path)
        assert result.returncode == 1

    def test_no_enumerators_returns_2(self, tmp_path: Path) -> None:
        """No enumerators returns 2 (existing behavior)."""
        workdir = Path(tmp_path)
        (workdir / "input.txt").write_text("Plain text without enumerators", encoding="utf-8")

        result = run_fallback(workdir)
        assert result.returncode == 2
        assert "no enumerators" in result.stdout
