"""Exercise the public Autofix step's output bindings against a caller checkout."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ACTION = Path(__file__).resolve().parents[2] / ".github/actions/autofix/action.yml"
CLEAN = 'def calc(x):\n    """Return a value."""\n    return x + 1\n'
FINDING = CLEAN.replace("x + 1", "x + missing_value")
UNFORMATTED = FINDING.replace("calc(x)", "calc( x )").replace("x + ", "x+")


@pytest.fixture
def caller(tmp_path: Path) -> Path:
    if missing := [tool for tool in ("bash", "git", "jq") if not shutil.which(tool)]:
        pytest.skip("Missing " + ", ".join(missing))
    repo = tmp_path / "caller"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src/calc.py").write_text(CLEAN)
    (repo / "ruff.toml").write_text('[lint]\nselect = ["F821"]\n')
    tools = tmp_path / "tools"
    tools.mkdir()
    # The contract does not exercise the networked optional type-stub setup.
    mypy = tools / "mypy"
    mypy.write_text("#!/bin/sh\nexit 0\n")
    mypy.chmod(0o755)
    if gfind := shutil.which("gfind"):
        (tools / "find").symlink_to(gfind)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def shell_step(caller: Path, step: dict[str, str]) -> subprocess.CompletedProcess[str]:
    output = caller.parent / step["id"]
    output.touch()
    env = {
        **os.environ,
        "PATH": os.pathsep.join(
            (str(caller.parent / "tools"), str(Path(sys.executable).parent), os.environ["PATH"])
        ),
        "GITHUB_OUTPUT": str(output),
        "RUNNER_TEMP": str(caller.parent),
    }
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
        cwd=caller,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def commit(caller: Path, *paths: str) -> None:
    subprocess.run(["git", "add", "--", *(paths or (".",))], cwd=caller, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=caller,
        check=True,
    )


def outputs(caller: Path) -> dict[str, str]:
    result = {}
    for name, binding in yaml.safe_load(ACTION.read_text())["outputs"].items():
        _, step_id, _, output_name = (
            binding["value"].removeprefix("${{ ").removesuffix(" }}").split(".")
        )
        pairs = dict(
            line.split("=", 1) for line in (caller.parent / step_id).read_text().splitlines()
        )
        result[name] = pairs[output_name]
    return result


def run_fixers(caller: Path) -> None:
    for step in yaml.safe_load(ACTION.read_text())["runs"]["steps"]:
        if step.get("id") in {"runfix", "mypyfix", "testfix", "numpyfix", "classify", "finalize"}:
            result = shell_step(caller, step)
            assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("source", "changed", "remaining"),
    [
        pytest.param(FINDING, "false", "1", id="uncorrected_finding"),
        pytest.param(CLEAN, "false", "0", id="clean_unchanged"),
        pytest.param(UNFORMATTED, "true", "1", id="formatter_and_finding"),
    ],
)
def test_actual_tools_emit_all_three_outputs(
    caller: Path, source: str, changed: str, remaining: str
) -> None:
    if missing := [
        tool for tool in ("ruff", "black", "isort", "docformatter") if not shutil.which(tool)
    ]:
        pytest.skip("Missing " + ", ".join(missing))
    target = caller / "src/calc.py"
    target.write_text(source)
    commit(caller)
    run_fixers(caller)
    assert outputs(caller) == {
        "changed": changed,
        "remaining_issues": remaining,
        "new_issues": remaining,
    }
    report = json.loads((caller / "autofix_report_enriched.json").read_text())
    assert report["changed"] == (changed == "true")
    assert report["classification"]["total"] == int(remaining)
    assert [
        entry["code"] for entry in json.loads((caller / "ruff_diagnostics.json").read_text())
    ] == ["F821"] * int(remaining)
    assert target.read_text() == (FINDING if remaining == "1" else CLEAN)
    if changed == "true":
        commit(caller, "src/calc.py")
        for step_id in ("classify", "finalize"):
            (caller.parent / step_id).unlink()
        run_fixers(caller)
        assert outputs(caller) == {"changed": "false", "remaining_issues": "1", "new_issues": "1"}


def classify(caller: Path) -> subprocess.CompletedProcess[str]:
    step = next(
        step
        for step in yaml.safe_load(ACTION.read_text())["runs"]["steps"]
        if step.get("id") == "classify"
    )
    return shell_step(caller, step)


def write_classifier(caller: Path, body: str) -> None:
    (caller / "scripts").mkdir()
    (caller / "scripts/classify_ruff.py").write_text(body)


def test_caller_classifier_retains_allowlisted_real_finding(caller: Path) -> None:
    if not shutil.which("ruff"):
        pytest.skip("Ruff is missing")
    (caller / "src/calc.py").write_text(FINDING)
    (caller / ".ruff-residual-allowlist.json").write_text('{"allow":[{"code":"F821"}]}')
    write_classifier(
        caller,
        """import json
import sys
from pathlib import Path

diagnostics = json.loads(Path(sys.argv[1]).read_text())
allow = json.loads(Path(sys.argv[2]).read_text())["allow"]
allowed = sum({"code": item["code"]} in allow for item in diagnostics)
assert [item["code"] for item in diagnostics] == ["F821"]
result = {"total": len(diagnostics), "new": len(diagnostics) - allowed, "allowed": allowed}
Path(sys.argv[3]).write_text(json.dumps(result))
""",
    )
    commit(caller)
    result = classify(caller)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (caller.parent / "classify").read_text() == "remaining_issues=1\nnew_issues=0\n"


def test_real_ruff_config_failure_cannot_report_clean(caller: Path) -> None:
    if not shutil.which("ruff"):
        pytest.skip("Ruff is missing")
    (caller / "ruff.toml").write_text("unknown_setting = 1\n")
    result = classify(caller)
    assert result.returncode != 0
    assert "unknown_setting" in result.stderr
    assert (caller.parent / "classify").read_text() == ""


@pytest.mark.parametrize(
    ("stdout", "status"),
    [("invalid JSON", 0), ("{}", 0), ("[]\n[]", 0), ("[]", 1), ('[{"code":1}]', 1)],
)
def test_malformed_ruff_result_cannot_report_clean(caller: Path, stdout: str, status: int) -> None:
    ruff = caller.parent / "tools/ruff"
    ruff.write_text("#!/bin/sh\n" f"printf '%s\\n' '{stdout}'\n" f"exit {status}\n")
    ruff.chmod(0o755)
    result = classify(caller)
    assert result.returncode != 0
    assert (caller.parent / "classify").read_text() == ""


@pytest.mark.parametrize(
    ("body", "allowlist"),
    [
        pytest.param("raise SystemExit(9)", None, id="tool_error"),
        pytest.param(
            "from pathlib import Path\nfrom sys import argv\n"
            "Path(argv[3]).write_text('broken JSON')",
            None,
            id="bad_json",
        ),
        pytest.param(
            "import sys\nfrom pathlib import Path\n"
            'Path(sys.argv[3]).write_text(\'{"total":0,"new":0}\')',
            None,
            id="false_clean",
        ),
        pytest.param(
            "from pathlib import Path\nfrom sys import argv\n"
            """Path(argv[3]).write_text('{"total":1,"new":1,"allowed":0,"by_code":[],"new_by_code":{}}')""",
            None,
            id="malformed_code_breakdown",
        ),
        pytest.param(
            "raise AssertionError('invalid allowlist reached caller helper')",
            '{"allow": "broken"}',
            id="bad_allowlist",
        ),
    ],
)
def test_bad_classifier_data_cannot_report_clean(
    caller: Path, body: str, allowlist: str | None
) -> None:
    if not shutil.which("ruff"):
        pytest.skip("Ruff is missing")
    (caller / "src/calc.py").write_text(FINDING)
    write_classifier(caller, body + "\n")
    if allowlist is not None:
        (caller / ".ruff-residual-allowlist.json").write_text(allowlist)
    result = classify(caller)
    assert result.returncode != 0
    assert "invalid allowlist reached caller helper" not in result.stderr
    assert (caller.parent / "classify").read_text() == ""
    assert not (caller / "autofix_report_enriched.json").exists()
