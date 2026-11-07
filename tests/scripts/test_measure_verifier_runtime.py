"""Exercise the measurement refusal boundary and real two-arm pytest execution."""

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from scripts import measure_verifier_runtime as measure


def fixture_repo(tmp_path, monkeypatch, *, change_source=False):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for key, value in [("user.name", "Measurement Test"), ("user.email", "test@example.invalid")]:
        subprocess.run(["git", "-C", str(repo), "config", key, value], check=True)
    (repo / "scripts/langchain").mkdir(parents=True)
    (repo / measure.VERIFIER).write_text(
        "def decision(value):\n    if value:\n        return True\n    return False\n"
    )
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\n[tool.coverage.run]\nbranch=true\nsource=["scripts"]\n'
    )
    (repo / "requirements.lock").write_text("# same common environment\n")
    workflow = repo / ".github/workflows/maint-88-verifier-runtime-comparison.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: fixture\n")
    for name in measure.SUITES:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "from scripts.langchain.pr_verifier import decision\n"
            "def test_decision():\n    assert decision(True)\n    assert not decision(False)\n"
        )

    def commit(message):
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True)
        return measure.git(repo, "rev-parse", "HEAD").decode().strip()

    baseline = commit("baseline")
    (repo / measure.SUITES[0]).write_text(
        (repo / measure.SUITES[0]).read_text() + "\n# candidate\n"
    )
    if change_source:
        (repo / measure.VERIFIER).write_text("def decision(value):\n    return not value\n")
    candidate = commit("candidate")
    monkeypatch.setattr(measure, "BASELINE", baseline)
    monkeypatch.setattr(measure, "CANDIDATE", candidate)
    return repo


def test_prepare_refuses_changed_production_and_reused_output(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch, change_source=True)
    with pytest.raises(ValueError, match="Production verifier bytes differ"):
        measure.prepare(repo, tmp_path / "out")
    with pytest.raises(FileExistsError):
        measure.prepare(repo, tmp_path / "out")


def test_real_arms_keep_one_environment_and_preserve_coverage(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    assert measure.run(output) == 0
    result = json.loads((output / "result.json").read_text())
    assert result["packages_unchanged"]
    assert result["outcome_comparison"] == {"successful": True, "gaps": []}
    assert result["arms"]["baseline"]["command"] == result["arms"]["candidate"]["command"]
    assert result["verifier_coverage"]["baseline_lines"] > 0
    assert result["verifier_coverage"]["candidate_branches"] > 0
    assert not result["verifier_coverage"]["lost_lines"]
    assert len(result["artifact_sha256"]) == 6


def test_coverage_loss_is_not_reported_as_equivalence():
    before = {
        "files": {
            measure.VERIFIER: {"executed_lines": [1, 2], "executed_branches": [[1, 2], [1, 3]]}
        }
    }
    after = {"files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, 2]]}}}
    result = measure.coverage_comparison(before, after)
    assert result["lost_lines"] == [2]
    assert result["lost_branches"] == [(1, 3)]


def test_fresh_graph_requires_explicit_candidate_fetch(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    subprocess.run(["git", "init", "-q", str(fresh)], check=True)
    subprocess.run(
        ["git", "-C", str(fresh), "fetch", "--quiet", str(repo), measure.BASELINE], check=True
    )
    subprocess.run(
        ["git", "-C", str(fresh), "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True
    )
    with pytest.raises(subprocess.CalledProcessError):
        measure.git(fresh, "archive", measure.CANDIDATE)
    # The workflow's retained-PR-head fetch supplies this exact object. A normal
    # branch-history fetch did not: the pre-squash head is a separate graph tip.
    subprocess.run(
        ["git", "-C", str(repo), "update-ref", "refs/pull/3950/head", measure.CANDIDATE], check=True
    )
    subprocess.run(
        ["git", "-C", str(fresh), "fetch", "--quiet", str(repo), "refs/pull/3950/head"], check=True
    )
    assert measure.git(fresh, "rev-parse", "FETCH_HEAD").decode().strip() == measure.CANDIDATE
    output = tmp_path / "fresh-output"
    measure.prepare(fresh, output)
    assert (
        json.loads((output / "manifest.json").read_text())["arms"]["candidate"]["commit"]
        == measure.CANDIDATE
    )


def test_source_archive_cannot_escape_its_arm(tmp_path, monkeypatch):
    repo = fixture_repo(tmp_path, monkeypatch)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo("../../escaped-source")
        member.size = 4
        tar.addfile(member, io.BytesIO(b"oops"))
    real_git = measure.git
    monkeypatch.setattr(
        measure,
        "git",
        lambda repo, *args: archive.getvalue() if args[0] == "archive" else real_git(repo, *args),
    )
    with pytest.raises(ValueError, match="escapes"):
        measure.prepare(repo, tmp_path / "out")
    assert not (tmp_path / "escaped-source").exists()


def test_prepare_entry_point_needs_no_installed_packages():
    # Preparation runs before pip install on a fresh setup-python interpreter.
    result = subprocess.run(
        [sys.executable, "-S", str(Path(measure.__file__).resolve()), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "prepare" in result.stdout


def test_source_archive_refuses_links(tmp_path):
    target = tmp_path / "arm"
    target.mkdir()
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../escaped-source"
        tar.addfile(member)
    with pytest.raises(ValueError, match="links and special"):
        measure.extract_source(archive.getvalue(), target)
    assert not (target / "link").exists()


@pytest.mark.parametrize(
    "entry",
    [
        None,
        {},
        {"executed_lines": [1]},
        {"executed_lines": None, "executed_branches": []},
        {"executed_lines": [True], "executed_branches": []},
        {"executed_lines": [0], "executed_branches": []},
        {"executed_lines": [-1], "executed_branches": []},
        {"executed_lines": ["1"], "executed_branches": []},
        {"executed_lines": [], "executed_branches": None},
        {"executed_lines": [], "executed_branches": [[1]]},
        {"executed_lines": [], "executed_branches": [[1, 2, 3]]},
        {"executed_lines": [], "executed_branches": [[True, 2]]},
        {"executed_lines": [], "executed_branches": [[1, 0]]},
        {"executed_lines": [], "executed_branches": [[1, "2"]]},
    ],
)
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_coverage_comparison_refuses_incomplete_or_invalid_lists(entry, arm):
    valid = {"files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}}}
    invalid = {"files": {measure.VERIFIER: entry}}
    before, after = (invalid, valid) if arm == "baseline" else (valid, invalid)
    with pytest.raises(ValueError, match=arm + ".*coverage"):
        measure.coverage_comparison(before, after)


def test_coverage_comparison_accepts_explicit_empty_lists_and_negative_exits():
    empty = {"files": {measure.VERIFIER: {"executed_lines": [], "executed_branches": []}}}
    populated = {
        "files": {measure.VERIFIER: {"executed_lines": [1, 2], "executed_branches": [[2, -1]]}}
    }
    assert measure.coverage_comparison(empty, empty)["lost_branches"] == []
    assert measure.coverage_comparison(populated, populated)["candidate_branches"] == 1


def _junit_receipt(tmp_path, *, name="receipt.xml", status="", omit_suite=False):
    path = tmp_path / name
    suites = measure.SUITES[:-1] if omit_suite else measure.SUITES
    path.write_text(
        '<testsuites><testsuite tests="3">'
        + "".join(
            f'<testcase classname="{suite[:-3].replace("/", ".")}" name="test_case" time="0">'
            f"{status}</testcase>"
            for suite in suites
        )
        + "</testsuite></testsuites>"
    )
    return path


@pytest.mark.parametrize(
    ("status", "outcome"),
    [("", "passed"), ("<failure/>", "failures"), ("<error/>", "errors"), ("<skipped/>", "skipped")],
)
def test_junit_retains_explicit_outcome_counts(tmp_path, status, outcome):
    receipt = measure.junit(_junit_receipt(tmp_path, status=status))
    for suite in measure.SUITES:
        row = receipt["per_file"][suite[:-3].replace("/", ".")]
        assert row["cases"] == 1
        assert row[outcome] == 1
        assert sum(row[key] for key in ("passed", "failures", "errors", "skipped")) == 1


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "defect",
    ["missing", "empty", "unreadable", "conflicting", "scope", "failure", "error", "skipped"],
)
def test_run_refuses_incomplete_or_unsuccessful_outcome_evidence(
    tmp_path, monkeypatch, arm, defect
):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)
    valid_coverage = {
        "files": {measure.VERIFIER: {"executed_lines": [1], "executed_branches": [[1, -1]]}}
    }

    def fake_pytest(command, *, cwd, **kwargs):
        (cwd / "coverage.json").write_text(json.dumps(valid_coverage))
        if cwd.name != arm or defect != "missing":
            status = {"failure": "<failure/>", "error": "<error/>", "skipped": "<skipped/>"}.get(
                defect, ""
            )
            if defect == "conflicting":
                status = "<failure/><skipped/>"
            receipt = _junit_receipt(
                cwd,
                name="pytest-junit.xml",
                status=status if cwd.name == arm else "",
                omit_suite=cwd.name == arm and defect == "scope",
            )
            if cwd.name == arm and defect == "empty":
                receipt.write_text("<testsuites/>")
            elif cwd.name == arm and defect == "unreadable":
                receipt.write_text("<testsuites>")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["arms"][arm]["exit_code"] == 0
    assert result["outcome_comparison"]["successful"] is False
    assert any(arm in reason for reason in result["outcome_comparison"]["gaps"])
    assert result["artifact_sha256"]
    if defect in ("unreadable", "conflicting"):
        assert "UNKNOWN" in result["arms"][arm]["junit_error"]


@pytest.mark.parametrize("defect", ["missing", "unreadable", "invalid-lists"])
def test_run_preserves_failed_coverage_comparison_receipt(tmp_path, monkeypatch, defect):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        coverage = cwd / "coverage.json"
        if defect == "unreadable":
            coverage.write_text("{")
        elif defect == "invalid-lists":
            coverage.write_text(json.dumps({"files": {measure.VERIFIER: {}}}))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(measure, "packages", lambda: [])
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["verifier_coverage"] is None
    assert result["coverage_error"]
    assert result["outcome_comparison"]["successful"] is True
    assert len(result["arms"]) == 2


@pytest.mark.parametrize("failure", ["exit", "packages", "lost-lines", "lost-branches"])
def test_existing_measurement_failure_checks_remain_required(tmp_path, monkeypatch, failure):
    repo = fixture_repo(tmp_path, monkeypatch)
    output = tmp_path / "out"
    measure.prepare(repo, output)

    def fake_pytest(command, *, cwd, **kwargs):
        _junit_receipt(cwd, name="pytest-junit.xml")
        entry = {"executed_lines": [1, 2], "executed_branches": [[1, 2], [2, -1]]}
        if cwd.name == "candidate":
            if failure == "lost-lines":
                entry["executed_lines"] = [1]
            elif failure == "lost-branches":
                entry["executed_branches"] = [[1, 2]]
        (cwd / "coverage.json").write_text(json.dumps({"files": {measure.VERIFIER: entry}}))
        return subprocess.CompletedProcess(command, 1 if failure == "exit" else 0)

    package_reads = iter([[], [{"name": "changed"}]] if failure == "packages" else [[], []])
    monkeypatch.setattr(measure, "packages", lambda: next(package_reads))
    monkeypatch.setattr(measure.subprocess, "run", fake_pytest)
    assert measure.run(output) == 1
    result = json.loads((output / "result.json").read_text())
    assert result["outcome_comparison"]["successful"] is True
    assert result["verifier_coverage"] is not None
