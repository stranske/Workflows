"""Protect the filesystem boundary of archived-base acceptance proofs."""

import io
import runpy
import shlex
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
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_real_archive_preserves_executable_proof_mode(tmp_path, archive_helper):
    repo = _committed_repo(tmp_path)
    executions = tmp_path / "proof-executions.txt"
    script = repo / "bin" / "proof.sh"
    script.parent.mkdir()
    script.write_text(
        "#!/bin/sh\n"
        "value=$(cat value.txt)\n"
        f"printf '%s\\n' \"$value\" >> {shlex.quote(str(executions))}\n"
        "printf 'archive-proof-%s\\n' \"$value\"\n"
        'test "$value" = "$(cat test_proof.txt)"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    (repo / "value.txt").write_text("base\n", encoding="utf-8")
    (repo / "test_proof.txt").write_text("head\n", encoding="utf-8")
    base = _commit(repo)
    target = tmp_path / "archive"
    target.mkdir()

    archive_helper["_archive_ref"](base, target, repo)

    extracted = target / "bin" / "proof.sh"
    assert extracted.read_bytes() == script.read_bytes()
    assert extracted.stat().st_mode & stat.S_IXUSR
    (repo / "value.txt").write_text("head\n", encoding="utf-8")
    _commit(repo)
    spec = archive_helper["DeliberateBreakSpec"](
        "executable-proof", "test_proof.txt", "value.txt", ("./bin/proof.sh",)
    )
    result = archive_helper["verify_spec"](spec, base=base, cwd=repo, enforce_tamper=False)

    # Both executions must survive cleanup; a fabricated verdict is insufficient.
    assert executions.read_text().splitlines() == ["head", "base"]
    assert result["verdict"] == "PASS"
    assert result["reason"] == "head-passed-base-failed"
    assert result["base_stdout"] == "archive-proof-base\n"
    assert (repo / "value.txt").read_text() == "head\n"
    assert script.read_bytes() == extracted.read_bytes()


def test_real_archive_does_not_materialize_external_symlink(tmp_path, archive_helper):
    repo = _committed_repo(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("external-original", encoding="utf-8")
    original = victim.read_bytes()
    executions = tmp_path / "test-executions.txt"
    (repo / "external-link").symlink_to(victim)
    (repo / "regular.txt").write_text("regular-base", encoding="utf-8")
    base = _commit(repo)
    target = tmp_path / "archive"
    target.mkdir()

    archive_helper["_archive_ref"](base, target, repo)

    assert (target / "regular.txt").read_text() == "regular-base"
    assert not (target / "external-link").exists()
    assert not (target / "external-link").is_symlink()
    (repo / "external-link").unlink()
    (repo / "regular.txt").write_text("regular-head", encoding="utf-8")
    (repo / "test_proof.py").write_text(
        "from pathlib import Path\n"
        "def test_proof():\n"
        f"    with Path({str(executions)!r}).open('a') as output:\n"
        "        output.write('called\\n')\n"
        "    assert not Path('external-link').is_symlink()\n"
        "    assert not Path('external-link').exists()\n"
        "    assert Path('regular.txt').read_text() == 'regular-head'\n",
        encoding="utf-8",
    )
    _commit(repo)
    spec = archive_helper["DeliberateBreakSpec"](
        "test_proof.py::test_proof",
        "test_proof.py",
        "regular.txt",
        archive_helper["_pytest_command"]("test_proof.py::test_proof"),
    )
    result = archive_helper["verify_spec"](spec, base=base, cwd=repo, enforce_tamper=False)

    assert executions.read_text().splitlines() == ["called", "called"]
    assert result["verdict"] == "PASS"
    assert result["reason"] == "head-passed-base-failed"
    assert "regular-base" in result["base_stdout"]
    assert victim.read_bytes() == original
    assert (repo / "regular.txt").read_text() == "regular-head"


@pytest.mark.parametrize("path_kind", ["parent", "absolute"])
def test_archive_escape_returns_broken_without_overwriting_external_file(
    tmp_path, monkeypatch, archive_helper, path_kind
):
    repo = _committed_repo(tmp_path)
    (repo / "app.py").write_text("VALUE = 0\n", encoding="utf-8")
    base = _commit(repo)
    (repo / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    executions = tmp_path / "test-executions.txt"
    (repo / "test_proof.py").write_text(
        "import app\nfrom pathlib import Path\n"
        "def test_proof():\n"
        f"    with Path({str(executions)!r}).open('a') as output:\n"
        "        output.write(str(app.VALUE) + '\\n')\n"
        "    assert app.VALUE == 1\n",
        encoding="utf-8",
    )
    _commit(repo)
    victim = tmp_path / "victim.txt"
    victim.write_text("external-original", encoding="utf-8")
    original = victim.read_bytes()
    member_name = "../victim.txt" if path_kind == "parent" else str(victim)
    # A real base archive still contains runnable code if the guard is broken.
    committed_archive = subprocess.run(
        ["git", "archive", "--format=tar", base], cwd=repo, check=True, capture_output=True
    )
    archive_bytes = io.BytesIO(committed_archive.stdout)
    with tarfile.open(fileobj=archive_bytes, mode="a") as archive:
        member = tarfile.TarInfo(member_name)
        payload = b"overwritten-by-archive"
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    # Substitute only git-archive transport. Head/base commands and extraction are real.
    real_run = subprocess.run
    archive_calls = []

    def run_command(command, **kwargs):
        if list(command)[:2] == ["git", "archive"]:
            archive_calls.append(list(command))
            return subprocess.CompletedProcess(command, 0, archive_bytes.getvalue(), b"")
        return real_run(command, **kwargs)

    monkeypatch.setattr(archive_helper["subprocess"], "run", run_command)
    temporary_directory = archive_helper["tempfile"].TemporaryDirectory
    monkeypatch.setattr(
        archive_helper["tempfile"],
        "TemporaryDirectory",
        lambda **kwargs: temporary_directory(dir=tmp_path, **kwargs),
    )
    spec = archive_helper["DeliberateBreakSpec"](
        "test_proof.py::test_proof",
        "test_proof.py",
        "app.py",
        archive_helper["_pytest_command"]("test_proof.py::test_proof"),
    )

    result = archive_helper["verify_spec"](spec, base=base, cwd=repo, enforce_tamper=False)

    assert victim.read_bytes() == original
    assert executions.read_text().splitlines() == ["1"]
    assert archive_calls == [["git", "archive", "--format=tar", base]]
    assert (repo / "app.py").read_text() == "VALUE = 1\n"
    assert result == {
        "verdict": "FAIL_BROKEN",
        "reason": "archive-extract-failed",
        "detail": f"unsafe archive path: {member_name}",
    }
