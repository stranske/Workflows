"""Protect the filesystem boundary of archived-base acceptance proofs."""

import io
import runpy
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest


@pytest.fixture(params=["", "templates/consumer-repo/"], ids=["root", "template"])
def archive_helper(request):
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / request.param / "scripts/check_deliberate_break.py"))


def _committed_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in [
        ["init", "-q"],
        ["config", "user.name", "Archive Proof"],
        ["config", "user.email", "archive@example.com"],
    ]:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return repo


def _commit(repo):
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True, capture_output=True)


def test_real_archive_preserves_executable_proof_mode(tmp_path, archive_helper):
    repo = _committed_repo(tmp_path)
    script = repo / "bin" / "proof.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nprintf 'archive-proof-ok\\n'\n", encoding="utf-8")
    script.chmod(0o755)
    _commit(repo)
    target = tmp_path / "archive"
    target.mkdir()

    archive_helper["_archive_ref"]("HEAD", target, repo)

    extracted = target / "bin" / "proof.sh"
    assert extracted.read_bytes() == script.read_bytes()
    assert extracted.stat().st_mode & stat.S_IXUSR
    result = subprocess.run([str(extracted)], capture_output=True, text=True, check=True)
    assert result.stdout == "archive-proof-ok\n"


def test_real_archive_does_not_materialize_external_symlink(tmp_path, archive_helper):
    repo = _committed_repo(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("external-original", encoding="utf-8")
    (repo / "external-link").symlink_to(victim)
    (repo / "regular.txt").write_text("regular-base", encoding="utf-8")
    _commit(repo)
    target = tmp_path / "archive"
    target.mkdir()

    archive_helper["_archive_ref"]("HEAD", target, repo)

    assert (target / "regular.txt").read_text() == "regular-base"
    assert not (target / "external-link").exists()
    assert not (target / "external-link").is_symlink()
    assert victim.read_text() == "external-original"


@pytest.mark.parametrize("path_kind", ["parent", "absolute"])
def test_archive_escape_returns_broken_without_overwriting_external_file(
    tmp_path, monkeypatch, archive_helper, path_kind
):
    repo = tmp_path / "repo"
    repo.mkdir()
    test_file = repo / "test_proof.py"
    test_file.write_text("def test_proof():\n    assert True\n", encoding="utf-8")
    victim = tmp_path / "victim.txt"
    victim.write_text("external-original", encoding="utf-8")
    member_name = "../victim.txt" if path_kind == "parent" else str(victim)
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w") as archive:
        member = tarfile.TarInfo(member_name)
        payload = b"overwritten-by-archive"
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    # Substitute only the git-archive transport boundary, using real tar extraction.
    real_run = subprocess.run

    def run_command(command, **kwargs):
        if list(command)[:2] == ["git", "archive"]:
            return subprocess.CompletedProcess(command, 0, archive_bytes.getvalue(), b"")
        if Path(kwargs["cwd"]) == repo:
            return subprocess.CompletedProcess(command, 0, "1 passed", "")
        return subprocess.CompletedProcess(command, 1, "FAILED test_proof.py::test_proof", "")

    monkeypatch.setattr(archive_helper["subprocess"], "run", run_command)
    temporary_directory = archive_helper["tempfile"].TemporaryDirectory
    monkeypatch.setattr(
        archive_helper["tempfile"],
        "TemporaryDirectory",
        lambda **kwargs: temporary_directory(dir=tmp_path, **kwargs),
    )
    spec = archive_helper["DeliberateBreakSpec"](
        "test_proof.py::test_proof", "test_proof.py", "app.py", ("proof-command",)
    )

    result = archive_helper["verify_spec"](spec, base="frozen-base", cwd=repo, enforce_tamper=False)

    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "archive-extract-failed",
        "detail": f"unsafe archive path: {member_name}",
    }
    assert victim.read_text() == "external-original"
    monkeypatch.setattr(archive_helper["subprocess"], "run", real_run)
