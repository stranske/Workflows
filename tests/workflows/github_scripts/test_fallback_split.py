from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fallback_split  # noqa: F401,E402

SCRIPT = SCRIPT_DIR / "fallback_split.py"


def run_fallback(tmp_path: Path) -> SimpleNamespace:
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


def test_fallback_split_generates_topics(tmp_path: Path) -> None:
    workdir = Path(tmp_path)
    (workdir / "input.txt").write_text(
        "1) Alpha topic\nBody line\n2) Beta topic\nAnother line\n", encoding="utf-8"
    )

    result = run_fallback(workdir)
    assert result.returncode == 0, result.stderr

    topics = json.loads((workdir / "topics.json").read_text(encoding="utf-8"))
    assert [topic["title"] for topic in topics] == ["Alpha topic", "Beta topic"]
    assert all(topic.get("fallback") for topic in topics)
    assert topics[0]["enumerator"].startswith("1")
    assert topics[1]["enumerator"].startswith("2")


def test_fallback_split_missing_input_returns_error(tmp_path: Path) -> None:
    result = run_fallback(tmp_path)
    assert result.returncode == 1
    assert "missing" in result.stdout
    assert not (Path(tmp_path) / "topics.json").exists()


def test_fallback_split_without_enumerators(tmp_path: Path) -> None:
    workdir = Path(tmp_path)
    (workdir / "input.txt").write_text("No enumerators here", encoding="utf-8")

    result = run_fallback(workdir)
    assert result.returncode == 2
    assert "no enumerators" in result.stdout
    assert not (workdir / "topics.json").exists()
