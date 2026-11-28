"""Exercise the standalone cosmetic repair's authored steps."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

CHECKOUT = Path(__file__).resolve().parents[2]


def _git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def _steps(template):
    workflow = yaml.safe_load(
        (CHECKOUT / "templates" / f"{template}.yml").read_text(encoding="utf-8")
    )
    (job,) = workflow["jobs"].values()
    return {step["name"]: step for step in job["steps"]}


def _commit(repo, message):
    _git(
        repo,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        message,
    )


def _fixture(tmp_path, name, text):
    repo = tmp_path / "repo"
    repo.mkdir()
    artifact = repo / name
    artifact.write_text(text, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "--", name)
    _commit(repo, "fixture")
    return repo, artifact


def _shell(repo, step, **env):
    subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=repo,
        env={**os.environ, **env},
        check=True,
        capture_output=True,
        text=True,
    )


def _capture_body(repo, steps, tmp_path):
    render = steps["Write pull request body"]
    publish = steps["Create pull request"]
    assert render["if"] == publish["if"]
    assert publish["uses"] == "peter-evans/create-pull-request@3ffccacd46053766916f087ce41d627c0b8cf2d1"
    assert "body" not in publish["with"]
    body_path = publish["with"]["body-path"].replace("${{ runner.temp }}", str(tmp_path))
    _shell(repo, render, RUNNER_TEMP=str(tmp_path))
    return Path(body_path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("template", "filename", "before", "after", "expected"),
    [
        (
            "cosmetic-repair",
            "odd ``` name\nEOF.py",
            "x=1\n",
            "x = 1\n",
            '    "odd ``` name\\nEOF.py"',
        ),
    ],
    ids=["cosmetic-odd-name"],
)
def test_standalone_pr_body_reads_real_changes(
    tmp_path, template, filename, before, after, expected
):
    repo, artifact = _fixture(tmp_path, filename, before)
    steps = _steps(template)
    output = tmp_path / "step-output"
    _shell(repo, steps["Check for changes"], GITHUB_OUTPUT=str(output))
    assert output.read_text() == "changed=false\n"
    # Exercise the renderer's fallback independently of its clean-run gate.
    assert "    See diff for details" in _capture_body(repo, steps, tmp_path)
    artifact.write_text(after, encoding="utf-8")
    output.write_text("")
    _shell(repo, steps["Check for changes"], GITHUB_OUTPUT=str(output))
    assert output.read_text() == "changed=true\n"
    body = _capture_body(repo, steps, tmp_path)
    assert expected in body
    assert "See diff for details" not in body


@pytest.mark.parametrize("template", ["cosmetic-repair"])
def test_standalone_pr_body_bounds_large_detail(tmp_path, template):
    repo, _ = _fixture(tmp_path, "initial.py", "x = 1\n")
    for index in range(110):
        path = repo / f"fixture-{index:03}.py"
        path.write_text("x = 1\n")
    _git(repo, "add", "--", ".")
    # The authored detector considers unstaged differences to tracked files.
    _commit(repo, "many paths")
    for path in repo.glob("fixture-*.py"):
        path.write_text("x = 2\n")
    body = _capture_body(repo, _steps(template), tmp_path)
    assert "fixture-000.py" in body
    assert "fixture-109.py" not in body
    assert body.count("Details truncated. See the pull request diff.") == 1
    assert len(body.encode()) < 12500


@pytest.mark.parametrize(
    ("step", "tool", "status", "output", "ok"),
    [
        ("Apply Black formatting", "black", 2, "", False),
        ("Apply isort import sorting", "isort", 1, "", False),
        ("Apply Ruff fixes", "ruff", 1, '[{"code":"F841"}]', True),
        ("Apply Ruff fixes", "ruff", 1, '[{"code":"E902"}]', False),
        ("Apply Ruff fixes", "ruff", 1, '[{"code":"F841"},{"code":"invalid-syntax"}]', False),
        ("Apply Ruff fixes", "ruff", 1, "[]", False),
        ("Apply Ruff fixes", "ruff", 1, "invalid JSON", False),
        ("Apply Ruff fixes", "ruff", 1, "", False),
        ("Apply Ruff fixes", "ruff", 2, "", False),
        ("Apply docformatter", "docformatter", 3, "", True),
        ("Apply docformatter", "docformatter", 1, "", False),
    ],
)
def test_cosmetic_repair_formatter_completion(tmp_path, step, tool, status, output, ok):
    command = tmp_path / tool
    command.write_text('#!/bin/sh\nprintf "%s\\n" "$OUTPUT"\nexit "$STATUS"\n')
    command.chmod(0o755)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}", "STATUS": str(status), "OUTPUT": output}
    steps = _steps("cosmetic-repair")
    if ok:
        _shell(tmp_path, steps[step], **env)
    else:
        with pytest.raises(subprocess.CalledProcessError):
            _shell(tmp_path, steps[step], **env)
