"""Exercise the measurement refusal boundary and real two-arm pytest execution."""

import importlib.util
import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "measure_verifier_runtime", Path("scripts/measure_verifier_runtime.py")
)
measure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure)


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
    with pytest.raises(tarfile.FilterError):
        measure.prepare(repo, tmp_path / "out")
    assert not (tmp_path / "escaped-source").exists()
