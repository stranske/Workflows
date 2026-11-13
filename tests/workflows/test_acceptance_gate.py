"""Named acceptance gates and the production keepalive stop decision."""

import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from scripts.runner_lib import acceptance_gate
from scripts.runner_lib.acceptance_gate import Command, extract_commands, run


@pytest.fixture
def gate_venv_is_test_python(monkeypatch):
    """Tests that stub run() need no real virtualenv; keep PATH changes test-local."""
    monkeypatch.setattr(
        acceptance_gate,
        "make_gate_venv",
        lambda: (Path(sys.executable), f"{sys.executable} -m pip"),
    )
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)


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


@pytest.mark.parametrize(
    "line", ["x" * 1_000_000, "é" * 1000 + "\n"], ids=["ascii-million", "unicode-multibyte"]
)
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
    privileged = workflow["jobs"]["preflight"]
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


def test_failed_preparation_keeps_aggregate_output_bounded(
    tmp_path, monkeypatch, gate_venv_is_test_python
):
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


def test_lock_only_preparation_installs_and_runs_gate(
    tmp_path, monkeypatch, capsys, gate_venv_is_test_python
):
    import zipfile

    wheel = tmp_path / "gate_fixture-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("gate_fixture.py", "VALUE = 4097\n")
        archive.writestr(
            "gate_fixture-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: gate-fixture\nVersion: 1.0\n",
        )
        archive.writestr(
            "gate_fixture-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr("gate_fixture-1.0.dist-info/RECORD", "")
    target = tmp_path / "installed"
    (tmp_path / "requirements.lock").write_text(f"--no-index\n{wheel}\n")
    (tmp_path / "test_gate.py").write_text(
        "from gate_fixture import VALUE\ndef test_value(): assert VALUE == 4097\n"
    )
    real_run = acceptance_gate.run
    calls = []

    def offline_run(commands, cwd):
        calls.extend(command.command for command in commands)
        # Tools are already provided by the test runtime. The project's lock
        # installation runs real pip; no package network access is used.
        if commands[0].command.endswith("pip install pytest ruff mypy"):
            return [acceptance_gate.Result(-1, commands[0].command, 0, "tools present")]
        isolated = [
            Command(command.criterion, f"{command.command} --target {target}")
            for command in commands
        ]
        return real_run(isolated, cwd)

    monkeypatch.setattr(acceptance_gate, "run", offline_run)
    commands = [Command(0, "pytest test_gate.py")]
    assert acceptance_gate.prepare(commands, tmp_path) == []
    monkeypatch.setenv("PYTHONPATH", str(target))
    results = real_run([Command(0, f"{sys.executable} -m pytest -q test_gate.py")], tmp_path)
    assert results[0].exit_code == 0, results[0].output
    assert any("-r requirements.lock" in call for call in calls)
    assert "Gate install source: requirements requirements.lock" in capsys.readouterr().out


def test_prepare_uses_declared_extras_lock_and_cov_like_ci(
    tmp_path, monkeypatch, capsys, gate_venv_is_test_python
):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="1"\n'
        "[project.optional-dependencies]\ndev=[]\ntest=[]\n"
        '[tool.pytest.ini_options]\naddopts="--cov=src"\n'
    )
    (tmp_path / "requirements.lock").write_text("do-not-install\n")
    calls = []

    def capture(commands, cwd):
        calls.extend(command.command for command in commands)
        return [acceptance_gate.Result(-1, commands[0].command, 0, "")]

    monkeypatch.setattr(acceptance_gate, "run", capture)
    assert acceptance_gate.prepare([Command(0, "pytest tests")], tmp_path) == []
    assert any("pytest-cov" in call for call in calls)
    assert any("-e '.[dev,test]'" in call for call in calls)
    assert any("-r requirements.lock" in call for call in calls)
    assert "editable project .[dev,test]" in capsys.readouterr().out


def test_prepare_warns_on_malformed_pyproject_and_keeps_requirements(
    tmp_path, monkeypatch, capsys, gate_venv_is_test_python
):
    (tmp_path / "pyproject.toml").write_text("[project\n")
    (tmp_path / "requirements.lock").write_text("fixture\n")
    calls = []

    def capture(commands, cwd):
        calls.extend(command.command for command in commands)
        return [acceptance_gate.Result(-1, commands[0].command, 0, "")]

    monkeypatch.setattr(acceptance_gate, "run", capture)
    assert acceptance_gate.prepare([Command(0, "pytest tests")], tmp_path) == []
    output = capsys.readouterr().out
    assert output.startswith("Gate install source warning: invalid pyproject.toml:")
    assert "Gate install source: requirements requirements.lock" in output
    assert any("-r requirements.lock" in call for call in calls)


def test_python_gates_install_and_run_in_an_isolated_gate_venv(tmp_path, monkeypatch):
    # The hosted runner's system python crashed every pytest gate at plugin load (exit 3),
    # so installs and gate commands must use a fresh virtualenv, never the launching python.
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    installs = []
    real_run = acceptance_gate.run

    def no_network(commands, cwd):
        installs.extend(command.command for command in commands)
        return [acceptance_gate.Result(-1, commands[0].command, 0, "")]

    monkeypatch.setattr(acceptance_gate, "run", no_network)
    assert acceptance_gate.prepare([Command(0, "pytest tests")], tmp_path) == []
    venv_root = Path(os.environ["VIRTUAL_ENV"])
    assert venv_root.name.startswith("acceptance-gate-venv-")
    assert not str(venv_root).startswith(str(tmp_path))  # never inside the PR checkout
    # Either the venv's own pip or the launcher's pip pointed at it (--python): both install there.
    assert installs and all(
        call.startswith(str(venv_root)) or f"--python {venv_root}" in call for call in installs
    ), installs
    probe = real_run([Command(0, "python -c 'import sys; print(sys.prefix)'")], tmp_path)[0]
    assert probe.exit_code == 0, probe.output
    assert Path(probe.output.strip()).resolve() == venv_root.resolve()
    assert Path(sys.prefix).resolve() != venv_root.resolve()


def test_unbuildable_gate_venv_fails_every_gate_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    def broken():
        raise OSError("ensurepip is not available")

    monkeypatch.setattr(acceptance_gate, "make_gate_venv", broken)
    results = acceptance_gate.prepare([Command(0, "pytest a"), Command(1, "ruff check")], tmp_path)
    assert [result.exit_code for result in results] == [127, 127]
    assert all("could not create a virtualenv: ensurepip" in result.output for result in results)


def test_node_test_and_python3_pytest_are_gates_but_node_ids_are_not():
    markdown = """
## Acceptance Criteria
- [ ] `node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js` passes.
- [ ] `python3 -m pytest tests/workflows/test_acceptance_gate.py -q` passes.
- [ ] `tests/workflows/test_acceptance_gate.py::test_run` is named but is not runnable.
- [ ] `node scripts/build.js` is a script, not a test runner.
"""
    assert extract_commands(markdown) == [
        Command(0, "node --test .github/scripts/__tests__/maint71_merge_sync_prs.test.js"),
        Command(1, "python3 -m pytest tests/workflows/test_acceptance_gate.py -q"),
    ]


def test_python3_pytest_gate_gets_the_gate_venv(tmp_path, monkeypatch, gate_venv_is_test_python):
    calls = []

    def capture(commands, cwd):
        calls.extend(command.command for command in commands)
        return [acceptance_gate.Result(-1, commands[0].command, 0, "")]

    monkeypatch.setattr(acceptance_gate, "run", capture)
    assert acceptance_gate.prepare([Command(0, "python3 -m pytest tests")], tmp_path) == []
    assert any(call.endswith("install pytest ruff mypy") for call in calls), calls


# Workflows#4523's acceptance criteria, verbatim (2026-11-12): criterion 0 pins an interpreter path.
ISSUE_4523_ACCEPTANCE = """
## Acceptance Criteria
- [ ] `/opt/anaconda3/bin/python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py tests/scripts/test_check_consumer_sync_drift.py tests/tools/test_llm_provider.py` exits 0 with >= 268 passed tests.
- [ ] `git merge-base --is-ancestor $(gh pr view 4516 --repo stranske/Workflows --json mergeCommit --jq .mergeCommit.oid) origin/main` exits 0.
- [ ] `docs/evidence/issue-4019/r3/mutations/mutation-receipts.json` exists on `origin/main` containing 27 verified mutation receipts.
"""


def test_a_path_pinned_interpreter_runs_as_python3_pytest_in_the_gate():
    commands = extract_commands(ISSUE_4523_ACCEPTANCE)
    assert commands, "the pinned-interpreter pytest criterion must be a gate"
    assert commands[0].criterion == 0
    assert commands[0].command.startswith(
        "python3 -m pytest tests/scripts/test_aggregate_agent_metrics.py"
    )
    assert all("/opt/anaconda3" not in command.command for command in commands)
    assert all(not command.command.startswith("git ") for command in commands)


def test_pinned_interpreter_forms_normalize_and_bare_forms_stay():
    markdown = """
## Acceptance Criteria
- [ ] `/usr/bin/python -m pytest tests/a.py` passes.
- [ ] `python3.13 -m pytest tests/b.py -q` passes.
- [ ] `python -m pytest tests/c.py` passes.
- [ ] `/opt/anaconda3/bin/python3 scripts/tool.py` is a script, not a test runner.
"""
    assert extract_commands(markdown) == [
        Command(0, "python3 -m pytest tests/a.py", "/usr/bin/python -m pytest tests/a.py"),
        Command(1, "python3 -m pytest tests/b.py -q", "python3.13 -m pytest tests/b.py -q"),
        Command(2, "python -m pytest tests/c.py"),
    ]


@pytest.mark.parametrize("interpreter", ["/opt/anaconda3/bin/python", "python3.11"])
@pytest.mark.parametrize("passes", [False, True], ids=["failed-gate", "passing-gate"])
@pytest.mark.parametrize("surface", ["source", "consumer-template"])
@pytest.mark.parametrize("markup", ["inline", "fenced"])
@pytest.mark.parametrize("companion", [False, True], ids=["single-gate", "passing-companion"])
def test_normalized_gate_matches_authored_acceptance_checkbox(
    tmp_path, interpreter, passes, surface, markup, companion
):
    """Real extractor/runner JSON must let the renderer reconcile the authored checkbox."""
    repo = Path(__file__).resolve().parents[2]
    root = repo if surface == "source" else repo / "templates/consumer-repo"
    gate_script = root / "scripts/runner_lib/acceptance_gate.py"
    renderer = root / ".github/scripts/keepalive_loop.js"
    original = f"{interpreter} -m pytest test_example.py -q"
    normalized = "python3 -m pytest test_example.py -q"
    other_command = "python3 -m pytest test_companion.py -q"
    authored = [original, other_command] if companion else [original]
    criterion = (
        " and ".join(f"`{command}`" for command in authored) + " pass"
        if markup == "inline"
        else "Run:\n  ```sh\n  " + "\n  ".join(authored) + "\n  ```"
    )
    body = f"## Acceptance Criteria\n- [x] {criterion}\n- [x] Human observation"
    (tmp_path / "test_example.py").write_text(f"def test_example():\n    assert {passes}\n")
    (tmp_path / "test_companion.py").write_text("def test_companion():\n    assert True\n")
    plan = {
        "markdown": body,
        "commands": json.loads(
            subprocess.check_output(
                [sys.executable, str(gate_script), "--extract"], input=body, text=True
            )
        ),
    }
    expected_commands = [{"criterion": 0, "command": normalized, "original_command": original}]
    if companion:
        expected_commands.append(
            {"criterion": 0, "command": other_command, "original_command": None}
        )
    assert plan["commands"] == expected_commands
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "results.json"
    plan_path.write_text(json.dumps(plan))
    subprocess.run(
        [
            sys.executable,
            str(gate_script),
            "--plan",
            str(plan_path),
            "--cwd",
            str(tmp_path),
            "--output",
            str(output_path),
        ],
        check=True,
    )
    gates = json.loads(output_path.read_text())
    result = gates["results"][0]
    assert result["exit_code"] == (0 if passes else 1)
    assert result["command"] == normalized
    assert result["original_command"] == original
    if companion:
        assert gates["results"][1]["criterion"] == 0
        assert gates["results"][1]["command"] == other_command
        assert gates["results"][1]["exit_code"] == 0
    rendered = json.loads(
        subprocess.check_output(
            [
                "node",
                "-e",
                "const fs = require('fs');"
                "const {renderDeterministicGates} = require(process.argv[1]);"
                "const gates = JSON.parse(fs.readFileSync(0, 'utf8'));"
                "const original = gates.commands[0].original_command;"
                "const normalized = gates.commands[0].command;"
                "console.log(JSON.stringify([gates.markdown, "
                "gates.markdown.replace(original, normalized)]"
                ".map(body => renderDeterministicGates(body, gates))));",
                str(renderer),
            ],
            input=json.dumps(gates),
            text=True,
            cwd=repo,
        )
    )
    for text, command in zip(rendered, [original, normalized], strict=True):
        expected = body.replace(original, command)
        if not passes:
            expected = expected.replace("- [x]", "- [ ]", 1)
        assert expected in text
        assert "- [x] Human observation" in text
        assert f"Deterministic gates: {int(passes) + int(companion)}/{len(authored)} passed" in text


@pytest.mark.parametrize("failure", ["timeout", "missing-executable"])
@pytest.mark.parametrize("interpreter", ["/opt/anaconda3/bin/python", "python3.11"])
@pytest.mark.parametrize("surface", ["source", "consumer-template"])
def test_normalized_gate_execution_error_unchecks_authored_criterion(
    tmp_path, monkeypatch, failure, interpreter, surface
):
    """Execution errors must retain the same checkbox identity as pytest failures."""
    repo = Path(__file__).resolve().parents[2]
    root = repo if surface == "source" else repo / "templates/consumer-repo"
    gate_script = root / "scripts/runner_lib/acceptance_gate.py"
    spec = importlib.util.spec_from_file_location("acceptance_gate_under_test", gate_script)
    gate = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, gate)
    spec.loader.exec_module(gate)
    original = f"{interpreter} -m pytest test_example.py"
    body = f"## Acceptance Criteria\n- [x] `{original}` passes\n- [x] Human observation"
    commands = gate.extract_commands(body)
    (tmp_path / "test_example.py").write_text(
        "import time\ndef test_example():\n    time.sleep(30)\n"
    )
    with monkeypatch.context() as execution:
        if failure == "timeout":
            execution.setattr(gate, "TIMEOUT_SECONDS", 0.1)
        else:
            execution.setenv("PATH", str(tmp_path))
        results = gate.run(commands, tmp_path)
    assert len(results) == 1
    result = results[0]
    assert result.exit_code == (124 if failure == "timeout" else 127)
    assert result.command == "python3 -m pytest test_example.py"
    assert result.original_command == original
    assert result.output
    if failure == "timeout":
        assert "Gate timed out." in result.output
    gates = {
        "markdown": body,
        "commands": [asdict(command) for command in commands],
        "results": [asdict(result) for result in results],
    }
    rendered = subprocess.check_output(
        [
            "node",
            "-e",
            "const fs = require('fs');"
            "const {renderDeterministicGates} = require(process.argv[1]);"
            "const gates = JSON.parse(fs.readFileSync(0, 'utf8'));"
            "process.stdout.write(renderDeterministicGates(gates.markdown, gates));",
            str(root / ".github/scripts/keepalive_loop.js"),
        ],
        input=json.dumps(gates),
        text=True,
        cwd=repo,
    )
    assert f"- [ ] `{original}` passes" in rendered
    assert "- [x] Human observation" in rendered
    assert "Deterministic gates: 0/1 passed" in rendered
    assert f"(exit {result.exit_code})" in rendered


@pytest.mark.parametrize("failure", ["venv", "install"])
@pytest.mark.parametrize("interpreter", ["/opt/anaconda3/bin/python", "python3.11"])
@pytest.mark.parametrize("surface", ["source", "consumer-template"])
def test_normalized_gate_preparation_failure_preserves_authored_command(
    tmp_path, monkeypatch, gate_venv_is_test_python, failure, interpreter, surface
):
    repo = Path(__file__).resolve().parents[2]
    root = repo if surface == "source" else repo / "templates/consumer-repo"
    gate_script = root / "scripts/runner_lib/acceptance_gate.py"
    spec = importlib.util.spec_from_file_location("acceptance_gate_under_test", gate_script)
    gate = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, gate)
    spec.loader.exec_module(gate)
    original = f"{interpreter} -m pytest tests/test_gate.py"
    body = f"## Acceptance Criteria\n- [x] `{original}` passes\n- [x] Human observation"
    commands = gate.extract_commands(body)

    def broken_venv():
        raise OSError("venv unavailable")

    setup_commands = []

    def failed_install(commands, cwd):
        assert cwd == tmp_path
        assert len(commands) == 1 and commands[0].criterion == -1
        setup_commands.append(commands[0].command)
        return [gate.Result(-1, commands[0].command, 1, "failed")]

    monkeypatch.setattr(gate, "run", failed_install)
    if failure == "venv":
        monkeypatch.setattr(gate, "make_gate_venv", broken_venv)
    else:
        monkeypatch.setattr(
            gate,
            "make_gate_venv",
            lambda: (Path(sys.executable), f"{sys.executable} -m pip"),
        )
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "results.json"
    appendix_path = tmp_path / "appendix.txt"
    plan_path.write_text(
        json.dumps({"markdown": body, "commands": [asdict(command) for command in commands]})
    )
    appendix_path.write_text("Original prompt")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(gate_script),
            "--plan",
            str(plan_path),
            "--cwd",
            str(tmp_path),
            "--output",
            str(output_path),
            "--appendix",
            str(appendix_path),
            "--prepare",
        ],
    )
    gate.main()
    gates = json.loads(output_path.read_text())
    assert len(gates["results"]) == 1
    result = gates["results"][0]
    assert result["exit_code"] == (127 if failure == "venv" else 1)
    assert result["command"] == "python3 -m pytest tests/test_gate.py"
    assert result["original_command"] == original
    assert "Gate environment setup failed:" in result["output"]
    assert len(setup_commands) == (0 if failure == "venv" else 1)
    assert appendix_path.read_text().startswith("Deterministic acceptance gates failed:")
    assert appendix_path.read_text().endswith("Original prompt")
    # Render the CLI's actual JSON artifact, including setup failures that bypass run().
    rendered = subprocess.check_output(
        [
            "node",
            "-e",
            "const fs = require('fs');"
            "const {renderDeterministicGates} = require(process.argv[1]);"
            "const gates = JSON.parse(fs.readFileSync(0, 'utf8'));"
            "process.stdout.write(renderDeterministicGates(gates.markdown, gates));",
            str(root / ".github/scripts/keepalive_loop.js"),
        ],
        input=json.dumps(gates),
        text=True,
        cwd=repo,
    )
    assert f"- [ ] `{original}` passes" in rendered
    assert "- [x] Human observation" in rendered
    assert "Deterministic gates: 0/1 passed" in rendered


# Plain-bullet acceptance sections, verbatim (Workflows#4454, Counter_Risk#1183; 2026-11-12).
ISSUE_4454_ACCEPTANCE = "## Acceptance Criteria\n- Named test: `tests/scripts/test_update_versions_from_pypi.py::TestConsumerRepoSampling::test_stale_check_is_window_aware` asserting, with `get_latest_pypi_version` and the clock patched: (a) Wednesday, pin 7.17.1, latest 7.17.2 published Tuesday → passes; (b) Monday, same pins → fails with `STALE VERSIONS`; (c) any day, pin older than the latest at the previous Monday → fails.\n- Runnable: `python3 -m pytest -q tests/scripts/test_update_versions_from_pypi.py` passes on a non-Monday with a release newer than the pins.\n- Deliberate-break → revert: restore the unconditional `current_version != latest_version` comparison → confirm `test_stale_check_is_window_aware` case (a) FAILS → revert.\n- Live: the first `Python Tests` run on an open PR after this merges, with pins still lagging a midweek release, is green; verify with `gh run view <run-id>` on that PR."
ISSUE_CR_1183_ACCEPTANCE = "## Acceptance Criteria\n\n- Named test: `pytest tests/test_runner_workbook.py -q` passes (including updated button expectations for D5 and I5).\n- Deliberate-break → revert: remove the new `RunnerActionButton` for `I5` from `scripts/build_runner_workbook.py` → confirm `tests/test_runner_workbook.py` FAILS → revert → passes."


def test_bullet_criteria_are_gates_when_the_section_has_no_checkbox():
    assert extract_commands(ISSUE_4454_ACCEPTANCE) == [
        Command(1, "python3 -m pytest -q tests/scripts/test_update_versions_from_pypi.py"),
    ]
    assert extract_commands(ISSUE_CR_1183_ACCEPTANCE) == [
        Command(0, "pytest tests/test_runner_workbook.py -q"),
    ]


def test_one_checkbox_keeps_checkbox_numbering_and_ignores_bullets():
    markdown = """
## Acceptance Criteria
- `pytest tests/bullet.py` is prose beside a checkbox list.
- [ ] `pytest tests/first.py` passes.
- [ ] `pytest tests/second.py` passes.
"""
    assert extract_commands(markdown) == [
        Command(0, "pytest tests/first.py"),
        Command(1, "pytest tests/second.py"),
    ]


def test_nested_bullets_belong_to_their_top_level_criterion():
    markdown = """
## Acceptance Criteria
- First criterion:
  - `pytest tests/nested.py` passes.
- `pytest tests/second.py` passes.
"""
    assert extract_commands(markdown) == [
        Command(0, "pytest tests/nested.py"),
        Command(1, "pytest tests/second.py"),
    ]
