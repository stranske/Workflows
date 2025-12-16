import contextlib
import importlib.util
import io
import json
import os
import pathlib
import runpy
import sys
from types import SimpleNamespace

import pytest

# Force serial execution - these tests write to shared files (input.txt, topics.json)
# The xdist_group marker ensures all tests in this file run in the same worker
pytestmark = [pytest.mark.serial, pytest.mark.xdist_group(name="chatgpt_parser")]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github/scripts/parse_chatgpt_topics.py"
TOPICS_PATH = pathlib.Path("topics.json")

SAMPLE_KEEPALIVE_ISSUES = """1. Agents keepalive: synthetic spec for parser validation

Labels: agents, agents:keepalive, agent:codex, ci

Why
Codex keepalive specifications should parse without coupling to the live Issues.txt file.

Scope
- Always create a new instruction comment for every keepalive round.
- Include hidden markers before the @codex instruction.
- Preserve the Scope/Tasks/Acceptance block in notifications.

Tasks
- In the keepalive poster (Codex Keepalive Sweep):
    - Generate a unique trace token for each round.
    - Compute the next round number via the helper.
    - Call agents-70-orchestrator.yml to dispatch the keepalive workflow.
    - Post the comment body with markers, the @codex instruction, and the Scope/Tasks/Acceptance block.
    - Authenticate with stranske-automation-bot credentials.
    - Append Round and TRACE values to the step summary.
- Update agents-70-orchestrator.yml guardrails when prerequisites change.

Acceptance criteria
- Each keepalive cycle adds a new comment with the hidden markers and @codex instruction.
- A repository_dispatch codex-pr-comment-command event fires for the new instruction comment and the connector acknowledges the command.
- The posted comment contains the current Scope/Tasks/Acceptance block.
- The poster's step summary shows Round and TRACE values.

Implementation notes
Keep the current author allow-list including stranske-automation-bot and maintainers.
When writing sample instructions, reference @{agent}, call out the PR kickoff comment template for onboarding, and remind teams about the required PR title prefix.

2. Documentation sync placeholder

Labels: docs, housekeeping

Why
Ensure the parser handles multiple topics within the same document.

Tasks
- Confirm summary sections render correctly.
- Capture acceptance entries for downstream automation.

Acceptance criteria
- Parser emits topics.json with this record.
- Acceptance criteria text is non-empty.
"""

_MODULE_SPEC = importlib.util.spec_from_file_location("parse_chatgpt_topics_module", SCRIPT)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise RuntimeError("Unable to load parse_chatgpt_topics module")
parse_module = importlib.util.module_from_spec(_MODULE_SPEC)
_MODULE_SPEC.loader.exec_module(parse_module)


def run_decode_cli(workdir: pathlib.Path, *args: str) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    script = REPO_ROOT / ".github/scripts/decode_raw_input.py"
    original_cwd = os.getcwd()
    original_argv = sys.argv
    try:
        os.chdir(workdir)
        sys.argv = [str(script), *args]
        with (
            contextlib.redirect_stdout(stdout_buffer),
            contextlib.redirect_stderr(stderr_buffer),
        ):
            try:
                runpy.run_path(str(script), run_name="__main__")
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


def run_parser_in_workdir(workdir: pathlib.Path, env: dict | None = None) -> SimpleNamespace:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    overrides = env or {}
    original_env: dict[str, str | None] = {key: os.environ.get(key) for key in overrides}
    original_cwd = os.getcwd()
    original_argv = sys.argv

    try:
        os.chdir(workdir)
        sys.argv = [str(SCRIPT)]
        os.environ.update({key: value for key, value in overrides.items() if value is not None})
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
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        os.chdir(original_cwd)
        sys.argv = original_argv

    return SimpleNamespace(
        returncode=code,
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def run_parser(text: str, env: dict | None = None) -> tuple[int, str, str, list[dict]]:
    """Helper to execute the parser script in-process and capture exit codes."""

    tmp = pathlib.Path("input.txt")
    tmp.write_text(text, encoding="utf-8")
    TOPICS_PATH.unlink(missing_ok=True)

    result = run_parser_in_workdir(pathlib.Path.cwd(), env=env)

    return (
        result.returncode,
        result.stdout,
        result.stderr,
        read_topics(),
    )


def read_topics() -> list[dict]:
    if not TOPICS_PATH.exists():
        return []
    return json.loads(TOPICS_PATH.read_text(encoding="utf-8"))


def test_parser_success_basic():
    code, out, err, topics = run_parser("1. First topic\n\nWhy\nBecause\n")
    assert code == 0, (code, out, err)
    assert len(topics) == 1
    assert topics[0]["title"] == "First topic"
    assert topics[0]["sections"]["why"].startswith("Because")


def test_parser_multiple_with_labels_and_sections():
    sample = (
        "1) Alpha feature rollout\nLabels: feat:alpha, risk:low\nWhy\nNeed early feedback.\n"
        "\n2: Beta hardening\nTasks\n- Add tests\n- Improve logging\n"
    )
    code, out, err, topics = run_parser(sample)
    assert code == 0
    assert [t["title"] for t in topics] == ["Alpha feature rollout", "Beta hardening"]
    assert topics[0]["labels"] == ["feat:alpha", "risk:low"]
    assert "Add tests" in topics[1]["sections"]["tasks"]


def test_parser_no_numbered_topics_exit_code():
    code, out, err, _topics = run_parser("No numbering here")
    # Expect mapped exit code 3
    assert code == 3, (code, out, err)


def test_parser_fallback_single_topic():
    code, out, err, topics = run_parser(
        "Single blob topic without numbers", env={"ALLOW_SINGLE_TOPIC": "1"}
    )
    assert code == 0, (code, out, err)
    assert len(topics) == 1
    assert topics[0]["title"].startswith("Single blob")


def test_parser_empty_input_exit_code():
    code, out, err, _topics = run_parser("")
    # empty -> exit code 2
    assert code == 2, (code, out, err)


def test_title_cleanup_markdown_and_punctuation():
    code, out, err, topics = run_parser("1) **Title with markdown.**")
    assert code == 0
    assert topics[0]["title"] == "Title with markdown"


def test_alpha_enumeration_and_continuity():
    sample = "A) Alpha topic\n\nB) Beta topic\n\nD) Delta skipped C\n"
    code, out, err, topics = run_parser(sample)
    assert code == 0
    enums = [t["enumerator"] for t in topics]
    assert enums == ["A", "B", "D"]
    continuity = [t["continuity_break"] for t in topics]
    # A (first) ok, B ok, D should flag break
    assert continuity == [False, False, True]


def test_alphanumeric_enumeration():
    sample = "A1) Composite one\nA2) Composite two\nA4) Composite four\n"
    code, out, err, topics = run_parser(sample)
    assert code == 0
    assert [t["enumerator"] for t in topics] == ["A1", "A2", "A4"]
    # For alphanum we do not enforce continuity (so all False)
    assert all(not t["continuity_break"] for t in topics)


def test_lowercase_alpha_enumeration():
    sample = "a) first\nb) second\nd) fourth skipped c\n"
    code, out, err, topics = run_parser(sample)
    assert code == 0
    enums = [t["enumerator"] for t in topics]
    assert enums == ["a", "b", "d"]
    continuity = [t["continuity_break"] for t in topics]
    assert continuity == [False, False, True]


def test_pipeline_handles_repository_issues_file(tmp_path: pathlib.Path) -> None:
    """End-to-end check that the parser handles Issues-style input.

    The real Issues.txt file bootstraps automation, so the test uses a
    synthetic sample to avoid coupling automation to documentation text.
    """

    workdir = tmp_path
    passthrough_source = workdir / "Issues.txt"
    passthrough_source.write_text(SAMPLE_KEEPALIVE_ISSUES, encoding="utf-8")

    decode_proc = run_decode_cli(
        workdir,
        "--passthrough",
        "--in",
        str(passthrough_source),
        "--source",
        "repo_file",
    )
    assert decode_proc.returncode == 0, decode_proc.stderr

    parser_proc = run_parser_in_workdir(workdir)
    assert parser_proc.returncode == 0, parser_proc.stderr

    topics_path = workdir / "topics.json"
    assert topics_path.exists(), "Parser must emit topics.json"
    topics = json.loads(topics_path.read_text(encoding="utf-8"))

    assert len(topics) >= 2, "Sample Issues spec should describe multiple topics"
    # Topics order may change; find the Agents 70 orchestrator topic by
    # the presence of the workflow filename in its tasks section.
    match = None
    for t in topics:
        tasks = t.get("sections", {}).get("tasks", "")
        if "agents-70-orchestrator.yml" in tasks:
            match = t
            break
    assert match is not None, "Could not find Agents 70 orchestrator topic in parsed topics"
    assert "agent:codex" in match["labels"]
    assert "agents-70-orchestrator.yml" in match["sections"]["tasks"]
    acceptance = match["sections"]["acceptance_criteria"].lower()
    assert "repository_dispatch" in acceptance
    assert "connector acknowledges" in acceptance
    assert "@{agent}" in match["sections"]["implementation_notes"]
    assert "PR kickoff comment" in match["sections"]["implementation_notes"]
    assert "PR title prefix" in match["sections"]["implementation_notes"]

    # Ensure every topic captures acceptance criteria to satisfy automation checks.
    assert all(topic["sections"]["acceptance_criteria"].strip() for topic in topics)

    debug = json.loads((workdir / "decode_debug.json").read_text(encoding="utf-8"))
    assert debug["source_used"] == "repo_file"


def test_split_numbered_items_unknown_style(monkeypatch) -> None:
    original_fullmatch = parse_module.re.fullmatch

    def fake_fullmatch(pattern, string, flags=0):  # type: ignore[override]
        if string == "B":
            return None
        return original_fullmatch(pattern, string, flags)

    monkeypatch.setattr(parse_module.re, "fullmatch", fake_fullmatch)
    sample = "A) First topic\nB) Second topic"
    items = parse_module._split_numbered_items(sample)
    assert items[1]["enumerator"] == "B"
    assert items[1]["continuity_break"] is False


def test_parse_sections_supports_label_separators() -> None:
    labels, sections, extras = parse_module._parse_sections(
        [
            "Labels: alpha; beta, gamma",
            "Why",
            "Rationale",
        ]
    )
    assert labels == ["alpha", "beta", "gamma"]
    assert sections["why"] == ["Rationale"]
    assert extras == []


def test_parse_text_single_topic_empty_raises_system_exit() -> None:
    with pytest.raises(SystemExit) as exc:
        parse_module.parse_text("   \n", allow_single_fallback=True)
    assert exc.value.code == 2


def test_parse_text_handles_string_lines(monkeypatch) -> None:
    def fake_split(_text: str):
        return [
            {
                "title": "Example",
                "lines": "Single line body",
                "enumerator": "1",
            }
        ]

    monkeypatch.setattr(parse_module, "_split_numbered_items", fake_split)
    topics = parse_module.parse_text("ignored")
    assert topics[0]["extras"] == "Single line body"


def test_parse_text_handles_unknown_line_type(monkeypatch) -> None:
    def fake_split(_text: str):
        return [
            {
                "title": "Example",
                "lines": None,
                "enumerator": "1",
            }
        ]

    monkeypatch.setattr(parse_module, "_split_numbered_items", fake_split)
    topics = parse_module.parse_text("ignored")
    assert topics[0]["extras"] == ""


def test_parser_main_missing_input_file(tmp_path: pathlib.Path) -> None:
    result = run_parser_in_workdir(tmp_path)
    assert result.returncode == 1
    assert "No input.txt" in result.stderr


def test_parser_main_maps_empty_input(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "input.txt").write_text("   ", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        parse_module.main()
    assert exc.value.code == 2


def test_parser_main_maps_no_numbered_topics(tmp_path: pathlib.Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "input.txt").write_text("No enumerators here", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        parse_module.main()
    assert exc.value.code == 3


def test_parser_main_reraises_other_system_exit(monkeypatch) -> None:
    def boom() -> list[dict]:
        raise SystemExit("Unexpected failure")

    monkeypatch.setattr(parse_module, "parse_topics", boom)
    with pytest.raises(SystemExit) as exc:
        parse_module.main()
    assert str(exc.value) == "Unexpected failure"


def test_parser_main_raises_on_empty_topics(monkeypatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setattr(parse_module, "parse_topics", lambda: [])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        parse_module.main()
    assert exc.value.code == 4


def test_parser_cli_error_prints_message(tmp_path: pathlib.Path) -> None:
    workdir = tmp_path
    (workdir / "input.txt").write_text("Plain text without numbers", encoding="utf-8")
    result = run_parser_in_workdir(workdir)
    assert result.returncode == 3
    assert result.stderr.strip() == "3"


def test_split_numbered_items_marks_numeric_continuity_break() -> None:
    sample = "1) Alpha milestone\n2) Beta milestone\n4) Delta skip"
    items = parse_module._split_numbered_items(sample)
    enums = [item["enumerator"] for item in items]
    assert enums == ["1", "2", "4"]
    breaks = [item["continuity_break"] for item in items]
    assert breaks == [False, False, True]


def test_parse_sections_collects_extras_and_aliases() -> None:
    labels, sections, extras = parse_module._parse_sections(
        [
            "Labels: feat:alpha; guardrail",
            "Intro context before sections",
            "Why",
            "Because the intake workflow needs coverage",
            "Implementation note",
            "Document guardrails",
        ]
    )
    assert labels == ["feat:alpha", "guardrail"]
    assert sections["why"] == ["Because the intake workflow needs coverage"]
    assert sections["implementation_notes"] == ["Document guardrails"]
    assert extras == ["Intro context before sections"]


def test_parse_text_guid_is_stable_for_repeated_titles() -> None:
    sample = "1) **Complex Title?!**\nWhy\nConsistency matters\n"
    first = parse_module.parse_text(sample)
    second = parse_module.parse_text(sample)
    assert first[0]["title"] == "Complex Title?!"
    assert first[0]["guid"] == second[0]["guid"]


def test_parse_text_fallback_preserves_body_in_extras() -> None:
    sample = "Single topic without enumerators\nBody line one\nBody line two"
    topics = parse_module.parse_text(sample, allow_single_fallback=True)
    assert len(topics) == 1
    assert topics[0]["title"] == "Single topic without enumerators"
    assert "Body line one" in topics[0]["extras"]
    assert "Body line two" in topics[0]["extras"]
