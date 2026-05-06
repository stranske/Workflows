from __future__ import annotations

import contextlib
import io
import json
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
DECODE_SCRIPT = SCRIPT_DIR / "decode_raw_input.py"
PARSE_SCRIPT = SCRIPT_DIR / "parse_chatgpt_topics.py"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "issue_intake_chatgpt"


def _run_script(path: Path, workdir: Path, argv: list[str]) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_cwd = os.getcwd()
    original_argv = sys.argv[:]
    original_env = os.environ.copy()
    try:
        os.chdir(workdir)
        sys.argv = [str(path), *argv]
        os.environ["ALLOW_SINGLE_TOPIC"] = "0"
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(path), run_name="__main__")
                code = 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(original_cwd)
        sys.argv = original_argv
        os.environ.clear()
        os.environ.update(original_env)
    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def _replay_raw_payload(tmp_path: Path, fixture_name: str) -> SimpleNamespace:
    payload = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    (tmp_path / "raw_input.json").write_text(json.dumps(payload), encoding="utf-8")

    decode = _run_script(DECODE_SCRIPT, tmp_path, ["--source", "raw_input"])
    if decode.returncode != 0:
        return SimpleNamespace(decode=decode, parse=None, topics=None)

    input_path = tmp_path / "input.txt"
    if not input_path.exists() or not input_path.read_text(encoding="utf-8").strip():
        (tmp_path / "topics.json").write_text("[]\n", encoding="utf-8")
        return SimpleNamespace(decode=decode, parse=None, topics=[])

    parse = _run_script(PARSE_SCRIPT, tmp_path, [])
    topics = None
    if (tmp_path / "topics.json").exists():
        topics = json.loads((tmp_path / "topics.json").read_text(encoding="utf-8"))
    return SimpleNamespace(decode=decode, parse=parse, topics=topics)


def test_valid_chatgpt_import_replays_to_one_topic(tmp_path: Path) -> None:
    result = _replay_raw_payload(tmp_path, "valid_import.txt")

    assert result.decode.returncode == 0
    assert result.parse.returncode == 0
    assert len(result.topics) == 1
    [topic] = result.topics
    assert topic["title"] == "Stabilize issue intake parser"
    assert topic["labels"] == ["agent:codex", "workflow"]
    assert "Replay this fixture" in topic["sections"]["tasks"]


def test_malformed_chatgpt_import_fails_gracefully(tmp_path: Path) -> None:
    result = _replay_raw_payload(tmp_path, "malformed_payload.txt")

    assert result.decode.returncode == 0
    assert result.parse.returncode == 3
    assert result.topics is None
    assert result.parse.stderr.strip() == "3"


def test_empty_chatgpt_import_is_noop(tmp_path: Path) -> None:
    result = _replay_raw_payload(tmp_path, "empty_payload.txt")

    assert result.decode.returncode == 0
    assert result.parse is None
    assert result.topics == []


def test_multi_issue_chatgpt_import_replays_all_topics(tmp_path: Path) -> None:
    result = _replay_raw_payload(tmp_path, "multi_issue_payload.txt")

    assert result.decode.returncode == 0
    assert result.parse.returncode == 0
    assert [topic["title"] for topic in result.topics] == [
        "Add importer fixture coverage",
        "Preserve decoded labels",
        "Handle imported acceptance criteria",
    ]
    assert "documentation" in result.topics[1]["labels"]
    assert "All three issues are emitted." in result.topics[2]["sections"]["acceptance_criteria"]
