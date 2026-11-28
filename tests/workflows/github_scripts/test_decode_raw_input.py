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

import decode_raw_input  # noqa: F401,E402

SCRIPT_PATH = SCRIPT_DIR / "decode_raw_input.py"


def run_decode_script(
    workdir: Path,
    *,
    argv: tuple[str, ...] = (),
    raw_payload: str | None = None,
) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    original_cwd = os.getcwd()
    original_argv = sys.argv[:]
    try:
        os.chdir(workdir)
        if raw_payload is not None:
            (workdir / "raw_input.json").write_text(raw_payload, encoding="utf-8")
        sys.argv = [str(SCRIPT_PATH), *argv]
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(SCRIPT_PATH), run_name="__main__")
                code = 0
            except SystemExit as exc:  # pragma: no cover - surfaced in returncode
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        os.chdir(original_cwd)
        sys.argv = original_argv

    debug_path = workdir / "decode_debug.json"
    debug: dict | None = None
    if debug_path.exists():
        debug = json.loads(debug_path.read_text(encoding="utf-8"))

    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
        input_path=workdir / "input.txt",
        debug_path=debug_path,
        debug=debug,
    )


def test_decode_json_payload_normalizes_text(tmp_path: Path) -> None:
    raw_text = (
        "\ufeff1)\tFirst topic Why explain\r\n"
        " Tasks - do thing\r"
        " Acceptance criteria confirm\u00a0"
        " Implementation notes include detail \u200b\u200d2) Second topic"
    )
    payload = json.dumps(raw_text)

    result = run_decode_script(tmp_path, raw_payload=payload)

    assert result.returncode == 0
    assert result.input_path.exists()
    decoded = result.input_path.read_text(encoding="utf-8")
    assert "\ufeff" not in decoded
    assert "\u00a0" not in decoded
    assert "\t" not in decoded
    assert decoded.endswith("\n")
    assert "2) Second topic" in decoded
    # Section headers should be split onto their own lines so downstream parser sees them
    assert result.debug is not None
    assert result.debug["source_used"] == "raw_input"
    assert result.debug["whitespace_normalization"]["bom"] == 1


def test_decode_passthrough_and_null_payload(tmp_path: Path) -> None:
    missing_passthrough = run_decode_script(tmp_path, argv=("--passthrough",))
    assert missing_passthrough.returncode == 0
    assert not missing_passthrough.input_path.exists()
    assert missing_passthrough.debug is None

    null_result = run_decode_script(tmp_path, raw_payload="null")
    assert null_result.returncode == 0
    assert not null_result.input_path.exists()
    assert null_result.debug is not None
    assert null_result.debug["rebuilt_len"] == 0


def test_passthrough_handles_repo_file_and_forced_split(tmp_path: Path) -> None:
    source_text = "Intro context 1) First item 2) Second item"
    source_path = tmp_path / "source.txt"
    source_path.write_text(source_text, encoding="utf-8")

    result = run_decode_script(
        tmp_path,
        argv=("--passthrough", "--in", str(source_path), "--source", "repo_file"),
    )

    assert result.returncode == 0
    decoded = result.input_path.read_text(encoding="utf-8")
    assert decoded.startswith("Intro context")
    # Fallback splitter should inject newlines before additional enumerators
    assert "\n2) Second item" in decoded

    assert result.debug is not None
    assert result.debug["source_used"] == "repo_file"
    # Enumerators packed onto one line should be detected so the parser can split them later
    assert "enumerators" in result.debug.get("applied", [])


def test_decode_applies_section_and_forced_heuristics(tmp_path: Path) -> None:
    structured = run_decode_script(
        tmp_path,
        raw_payload=json.dumps(
            "Intro text Why sections Implementation notes details 1) Alpha topic 2) Beta topic"
        ),
    )
    assert structured.returncode == 0
    assert structured.debug is not None
    assert "sections" in structured.debug["applied"]
    assert "enumerators" in structured.debug["applied"]

    forced_dir = tmp_path / "forced"
    forced_dir.mkdir()
    forced_result = run_decode_script(
        forced_dir,
        raw_payload=json.dumps("1) Alpha 2) Beta"),
    )
    assert forced_result.returncode == 0
    assert forced_result.debug is not None
    assert "forced_split" in forced_result.debug["applied"]
    assert forced_result.input_path.read_text(encoding="utf-8").count("\n") >= 2


def test_decode_gracefully_handles_missing_inputs(tmp_path: Path) -> None:
    result = run_decode_script(tmp_path)
    assert result.returncode == 0
    assert not result.input_path.exists()
    assert not result.debug_path.exists()


def test_json_string_decoding_writes_input_and_debug(tmp_path: Path) -> None:
    raw_text = "First topic\nSecond topic"

    result = run_decode_script(tmp_path, raw_payload=json.dumps(raw_text))

    assert result.returncode == 0
    assert result.input_path.read_text(encoding="utf-8") == "First topic\nSecond topic\n"
    assert result.debug == {
        "raw_len": len(raw_text),
        "raw_newlines": 1,
        "rebuilt_len": len(raw_text),
        "rebuilt_newlines": 1,
        "applied": [],
        "raw_enum_count": 0,
        "raw_enum_distinct": [],
        "rebuilt_enum_count": 0,
        "rebuilt_enum_distinct": [],
        "whitespace_normalization": {
            "carriage_returns": 0,
            "crlf_pairs": 0,
            "bom": 0,
            "nbsp": 0,
            "zws": 0,
            "tabs": 0,
            "other_zero_width": 0,
        },
        "source_used": "raw_input",
    }


def test_plain_text_fallback_when_raw_input_is_not_json(tmp_path: Path) -> None:
    raw_payload = "not valid json {"

    result = run_decode_script(tmp_path, raw_payload=raw_payload)

    assert result.returncode == 0
    assert result.input_path.read_text(encoding="utf-8") == f"{raw_payload}\n"
    assert result.debug is not None
    assert result.debug["raw_len"] == len(raw_payload)
    assert result.debug["rebuilt_len"] == len(raw_payload)
    assert result.debug["applied"] == []
    assert result.debug["source_used"] == "raw_input"


def test_passthrough_missing_input_file_returns_without_outputs(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.txt"

    result = run_decode_script(
        tmp_path,
        argv=("--passthrough", "--in", str(missing_file), "--source", "repo_file"),
    )

    assert result.returncode == 0
    assert not result.input_path.exists()
    assert not result.debug_path.exists()
    assert result.debug is None


def test_passthrough_present_input_file_writes_normalized_output(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    source_path.write_text("Line one\nLine two", encoding="utf-8")

    result = run_decode_script(
        tmp_path,
        argv=("--passthrough", "--in", str(source_path), "--source", "source_url"),
    )

    assert result.returncode == 0
    assert result.input_path.read_text(encoding="utf-8") == "Line one\nLine two\n"
    assert result.debug is not None
    assert result.debug["source_used"] == "source_url"
    assert result.debug["raw_newlines"] == 1
    assert result.debug["rebuilt_newlines"] == 1


def test_whitespace_normalization_covers_bom_line_endings_and_invisible_chars(
    tmp_path: Path,
) -> None:
    raw_text = (
        "\ufeffAlpha\r\nBeta\rGamma\u00a0Delta\u200b" "Epsilon\u200cZeta\u200dEta\u2060Theta\tIota"
    )

    result = run_decode_script(tmp_path, raw_payload=json.dumps(raw_text))

    assert result.returncode == 0
    assert (
        result.input_path.read_text(encoding="utf-8")
        == "Alpha\nBeta\nGamma DeltaEpsilonZetaEtaTheta Iota\n"
    )
    assert result.debug is not None
    assert result.debug["applied"] == []
    assert result.debug["raw_newlines"] == 2
    assert result.debug["rebuilt_newlines"] == 2
    assert result.debug["whitespace_normalization"] == {
        "carriage_returns": 1,
        "crlf_pairs": 1,
        "bom": 1,
        "nbsp": 1,
        "zws": 1,
        "tabs": 1,
        "other_zero_width": 4,
    }


def test_enumerator_and_section_reconstruction_records_debug_diagnostics(
    tmp_path: Path,
) -> None:
    raw_text = (
        "1) Alpha Why rationale Tasks do it Acceptance criteria pass "
        "Implementation notes note 2) Beta Why second rationale"
    )

    result = run_decode_script(tmp_path, raw_payload=json.dumps(raw_text))

    assert result.returncode == 0
    assert result.input_path.read_text(encoding="utf-8") == (
        "1) Alpha\n"
        "Why\n"
        "rationale\n"
        "Tasks\n"
        "do it\n"
        "Acceptance criteria\n"
        "pass\n"
        "Implementation notes\n"
        "note \n"
        "2) Beta\n"
        "Why\n"
        "second rationale\n"
    )
    assert result.debug is not None
    assert result.debug["applied"] == ["enumerators", "sections"]
    assert result.debug["raw_newlines"] == 0
    assert result.debug["rebuilt_newlines"] == 11
    assert result.debug["raw_enum_count"] == 2
    assert result.debug["raw_enum_distinct"] == ["1", "2"]
    assert result.debug["rebuilt_enum_count"] == 2
    assert result.debug["rebuilt_enum_distinct"] == ["1", "2"]
