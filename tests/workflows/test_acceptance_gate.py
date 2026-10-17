"""Named acceptance gates and the production keepalive stop decision."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.runner_lib import acceptance_gate
from scripts.runner_lib.acceptance_gate import Command, extract_commands, run


def test_extract_commands_inline_fenced_and_non_commands():
    markdown = """
## Tasks
- [ ] `pytest ignored_task.py`
## Acceptance Criteria
`pytest ignored_paragraph.py`
- [ ] `pytest tests/test_gate.py` passes, with `tests/test_gate.py` and `PASS`.
- [x] Run:
  ```sh
  python -m pytest tests/test_other.py
  npm test
  ```
- [ ] `npm run lint`, `ruff check .`, `mypy src`, and `make test` pass.

Unrelated `pytest ignored_paragraph.py`
## Non-Goals
- [ ] `pytest ignored_non_goal.py`
"""
    assert extract_commands(markdown) == [
        Command(0, "pytest tests/test_gate.py"),
        Command(1, "python -m pytest tests/test_other.py"),
        Command(1, "npm test"),
        Command(2, "npm run lint"),
        Command(2, "ruff check ."),
        Command(2, "mypy src"),
        Command(2, "make test"),
    ]


def test_ignore_fenced_markdown_examples_outside_acceptance():
    assert extract_commands("```md\n## Acceptance Criteria\n- [ ] `pytest fake.py`\n```") == []


@pytest.mark.parametrize(
    ("opening", "interior", "closing"),
    [
        ("````sh", "```", "````"),
        ("```sh", "~~~", "```"),
        ("```sh", "```not-a-closing-fence", "````"),
        ("~~~~sh", "~~~", "~~~~"),
    ],
)
def test_fenced_commands_require_matching_closing_marker(opening, interior, closing):
    markdown = f"""
## Acceptance Criteria
- [ ] Run:
  {opening}
  {interior}
  pytest tests/test_fenced.py
  {closing}
- [ ] `npm test` passes.
"""
    assert extract_commands(markdown) == [
        Command(0, "pytest tests/test_fenced.py"),
        Command(1, "npm test"),
    ]


def test_short_fence_does_not_expose_example_acceptance_criteria():
    markdown = """
````markdown
```
## Acceptance Criteria
- [ ] `pytest fake.py`
````
## Acceptance Criteria
- [ ] `pytest real.py`
"""
    assert extract_commands(markdown) == [Command(0, "pytest real.py")]


@pytest.mark.parametrize("status", [0, 3])
def test_run_captures_pass_fail_and_last_40_lines(tmp_path, status):
    script = tmp_path / "gate.py"
    script.write_text(f"for i in range(45): print(i)\nraise SystemExit({status})\n")
    result = run([Command(0, f"{sys.executable} {script.name}")], tmp_path)[0]
    assert result.exit_code == status
    assert result.output.splitlines() == [str(i) for i in range(5, 45)]


def test_timeout_and_missing_executable_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance_gate, "TIMEOUT_SECONDS", 0.1)
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n")
    results = run(
        [Command(0, f"{sys.executable} {script.name}"), Command(1, "missing-gate-executable")],
        tmp_path,
    )
    assert results[0].exit_code == 124
    assert "timed out" in results[0].output
    assert results[1].exit_code == 127


def test_commands_do_not_inherit_credentials(tmp_path, monkeypatch):
    credentials = [
        "GATE_SECRET",
        "SERVICE_BOT_PAT",
        "ACTIONS_BOT_PAT",
        "OWNER_PR_PAT",
        "AGENTS_AUTOMATION_PAT",
        "CUSTOM_PASSWORD",
        "ACTIONS_RUNTIME_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "GITHUB_ENV",
        "GITHUB_OUTPUT",
    ]
    for name in credentials:
        monkeypatch.setenv(name, "sensitive")
    monkeypatch.setenv("CI", "true")
    script = tmp_path / "env.py"
    script.write_text(
        f"import os\nassert not set({credentials!r}) & os.environ.keys()\n"
        "assert os.environ['CI'] == 'true'\n"
    )
    assert run([Command(0, f"{sys.executable} {script.name}")], tmp_path)[0].exit_code == 0


def test_cli_records_per_criterion_failure_and_prepends_prompt(tmp_path):
    (tmp_path / "test_example.py").write_text("def test_example():\n    assert False\n")
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "markdown": "## Acceptance Criteria\n- [ ] `pytest test_example.py` passes",
                "head_sha": "tested-head",
                "source_hash": "tested-criteria",
            }
        )
    )
    output = tmp_path / "results.json"
    appendix = tmp_path / "appendix.txt"
    appendix.write_text("Original prompt")
    subprocess.run(
        [
            sys.executable,
            str(Path(acceptance_gate.__file__)),
            "--plan",
            str(plan),
            "--cwd",
            str(tmp_path),
            "--output",
            str(output),
            "--appendix",
            str(appendix),
        ],
        check=True,
    )
    recorded = json.loads(output.read_text())
    assert recorded["head_sha"] == "tested-head"
    assert recorded["source_hash"] == "tested-criteria"
    assert recorded["results"][0]["criterion"] == 0
    assert recorded["results"][0]["exit_code"] == 1
    assert "AssertionError" in recorded["results"][0]["output"]
    assert appendix.read_text().startswith("Deterministic acceptance gates failed:")
    assert appendix.read_text().endswith("Original prompt")


def test_stop_condition_refuses_failing_gate():
    """Exercise the JS stop path through the real Python extractor (mutation gate)."""
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "node",
            "--test",
            "--test-name-pattern=deterministic failing gate",
            ".github/scripts/__tests__/keepalive-loop.test.js",
        ],
        cwd=repo,
        env={**os.environ, "PYTHON": sys.executable},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("line", ["x" * 1_000_000, "é" * 1000 + "\n"])
def test_output_is_bounded_by_bytes_per_command_and_in_total(tmp_path, line):
    script = tmp_path / "verbose.py"
    script.write_text(f"print({line!r} * 50)\n")
    results = run([Command(i, f"{sys.executable} {script.name}") for i in range(6)], tmp_path)
    assert all(result.exit_code == 0 for result in results)
    assert all(len(result.output.encode()) <= acceptance_gate.OUTPUT_BYTES for result in results)
    assert (
        sum(len(result.output.encode()) for result in results) <= acceptance_gate.TOTAL_OUTPUT_BYTES
    )
    assert all(len(result.output.splitlines()) <= 40 for result in results)
    assert results[0].output


def test_workflow_isolates_pr_commands_from_privileged_mark_running():
    import yaml

    repo = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((repo / ".github/workflows/agents-keepalive-loop.yml").read_text())
    isolated = workflow["jobs"]["acceptance-gates"]
    privileged = workflow["jobs"]["mark-running"]
    assert isolated["runs-on"] == "ubuntu-latest"
    assert isolated["permissions"] == {"contents": "read"}
    assert "acceptance-gates" in privileged["needs"]
    assert "secrets." not in json.dumps(isolated)
    assert "setup-api-client" not in json.dumps(isolated)
    assert "acceptance_gate.py --prepare" in json.dumps(isolated)
    assert "acceptance_gate.py --prepare" not in json.dumps(privileged)
    for step in isolated["steps"]:
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] is False
    upload = next(
        step
        for step in isolated["steps"]
        if step.get("uses", "").startswith("actions/upload-artifact@")
    )
    download = next(
        step
        for step in privileged["steps"]
        if step["name"] == "Download isolated acceptance results"
    )
    assert upload["with"]["name"] == download["with"]["name"]
    assert "overwrite" not in upload["with"]


def test_failed_preparation_keeps_aggregate_output_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(
        acceptance_gate,
        "run",
        lambda commands, cwd: [acceptance_gate.Result(-1, commands[0].command, 1, "x" * 2048)],
    )
    commands = [Command(i, "pytest test_gate.py") for i in range(10)]
    results = acceptance_gate.prepare(commands, tmp_path)
    assert len(results) == len(commands)
    assert all(result.exit_code == 1 for result in results)
    assert (
        sum(len(result.output.encode()) for result in results) <= acceptance_gate.TOTAL_OUTPUT_BYTES
    )
