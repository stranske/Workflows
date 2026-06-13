from __future__ import annotations

import py_compile
import re
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/health-40-repo-selfcheck.yml"


def _extract_aggregate_heredoc() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*-\s+name:\s+Aggregate & Summarize\n"
        r".*?^\s*python\s+-\s+<<'PY'\n"
        r"(?P<body>.*?)"
        r"^\s*PY\n",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match, "Aggregate & Summarize Python heredoc not found"
    return textwrap.dedent(match.group("body"))


def test_aggregate_python_heredoc_compiles() -> None:
    body = _extract_aggregate_heredoc()

    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        py_compile.compile(handle.name, doraise=True)


def test_close_tracker_gate_requires_positive_checks_ran_signal() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'handle.write("checks_ran=true\\n")' in text
    assert re.search(
        r"-\s+name:\s+Close failure tracker issue\b"
        r"(?s:.*?)"
        r"steps\.aggregate\.outputs\.checks_ran\s*==\s*'true'\s*&&\s*"
        r"steps\.aggregate\.outputs\.has_errors\s*!=\s*'true'\s*&&\s*"
        r"steps\.aggregate\.outputs\.has_warnings\s*!=\s*'true'",
        text,
        flags=re.DOTALL,
    )
