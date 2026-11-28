import os
import pathlib
import subprocess
import tempfile

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "update-floating-tag.sh"


def _run(cmd, cwd, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True)


def _init_repo(path: pathlib.Path):
    _run(["git", "init"], cwd=path)
    _run(["git", "config", "user.name", "Test User"], cwd=path)
    _run(["git", "config", "user.email", "test@example.com"], cwd=path)
    _run(["git", "config", "commit.gpgsign", "false"], cwd=path)


def _commit_file(path: pathlib.Path, filename: str, content: str, message: str) -> str:
    file_path = path / filename
    file_path.write_text(content, encoding="utf-8")
    _run(["git", "add", filename], cwd=path)
    _run(["git", "commit", "-m", message], cwd=path)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()
    return sha


def _tag(path: pathlib.Path, name: str, ref: str):
    _run(["git", "tag", name, ref], cwd=path)


def test_update_floating_tag_tracks_highest_v1_release(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        commit_v1_0_0 = _commit_file(repo_path, "file.txt", "v1.0.0\n", "v1.0.0")
        _tag(repo_path, "v1.0.0", commit_v1_0_0)

        commit_v1_2_0 = _commit_file(repo_path, "file.txt", "v1.2.0\n", "v1.2.0")
        _tag(repo_path, "v1.2.0", commit_v1_2_0)

        env = os.environ.copy()
        env["DRY_RUN"] = "1"

        _run(["bash", str(SCRIPT_PATH), "v1", "v1."], cwd=repo_path, env=env)

        floating_target = subprocess.check_output(
            ["git", "rev-parse", "v1"], cwd=repo_path, text=True
        ).strip()

        assert floating_target == commit_v1_2_0


def test_update_floating_tag_creates_floating_tag_when_missing(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        commit_v1_1_0 = _commit_file(repo_path, "file.txt", "v1.1.0\n", "v1.1.0")
        _tag(repo_path, "v1.1.0", commit_v1_1_0)

        env = os.environ.copy()
        env["DRY_RUN"] = "1"

        completed = subprocess.run(
            ["git", "rev-parse", "v1"],
            cwd=repo_path,
            capture_output=True,
        )
        assert completed.returncode != 0

        _run(["bash", str(SCRIPT_PATH), "v1", "v1."], cwd=repo_path, env=env)

        floating_target = subprocess.check_output(
            ["git", "rev-parse", "v1"], cwd=repo_path, text=True
        ).strip()

        assert floating_target == commit_v1_1_0


def test_update_floating_tag_requires_tagged_commit(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        commit_v1_0_0 = _commit_file(repo_path, "file.txt", "v1.0.0\n", "v1.0.0")
        _tag(repo_path, "v1.0.0", commit_v1_0_0)

        commit_unreleased = _commit_file(repo_path, "file.txt", "draft\n", "draft change")

        env = os.environ.copy()
        env["DRY_RUN"] = "1"

        completed = subprocess.run(
            ["bash", str(SCRIPT_PATH), "v1", "v1.", commit_unreleased],
            cwd=repo_path,
            env=env,
            capture_output=True,
        )

        assert completed.returncode != 0
        assert "not tagged with v1.* release" in completed.stderr.decode()


def test_update_floating_tag_skips_when_missing_release_and_allowed(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        _commit_file(repo_path, "file.txt", "initial\n", "initial")

        env = os.environ.copy()
        env["DRY_RUN"] = "1"
        env["ALLOW_MISSING_RELEASES"] = "1"

        completed = subprocess.run(
            ["bash", str(SCRIPT_PATH), "v1", "v1."],
            cwd=repo_path,
            env=env,
            capture_output=True,
        )

        assert completed.returncode == 0
        floating_missing = subprocess.run(
            ["git", "rev-parse", "v1"],
            cwd=repo_path,
            capture_output=True,
        )

        assert floating_missing.returncode != 0


def test_update_floating_tag_updates_existing_tag_to_latest_release(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        commit_v1_0_0 = _commit_file(repo_path, "file.txt", "v1.0.0\n", "v1.0.0")
        _tag(repo_path, "v1.0.0", commit_v1_0_0)
        _tag(repo_path, "v1", commit_v1_0_0)

        commit_v1_3_0 = _commit_file(repo_path, "file.txt", "v1.3.0\n", "v1.3.0")
        _tag(repo_path, "v1.3.0", commit_v1_3_0)

        env = os.environ.copy()
        env["DRY_RUN"] = "1"

        _run(["bash", str(SCRIPT_PATH), "v1", "v1."], cwd=repo_path, env=env)

        floating_target = subprocess.check_output(
            ["git", "rev-parse", "v1"], cwd=repo_path, text=True
        ).strip()

        assert floating_target == commit_v1_3_0


def test_update_floating_tag_never_moves_back_to_an_older_release(monkeypatch):
    """Round-2 D11: a late run for an older tag must not roll v1 backwards."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = pathlib.Path(temp_dir)
        _init_repo(repo_path)

        commit_v1_9 = _commit_file(repo_path, "file.txt", "v1.9.0\n", "v1.9.0")
        _tag(repo_path, "v1.9.0", commit_v1_9)
        commit_v1_10 = _commit_file(repo_path, "file.txt", "v1.10.0\n", "v1.10.0")
        _tag(repo_path, "v1.10.0", commit_v1_10)
        _tag(repo_path, "v1", commit_v1_10)

        env = os.environ.copy()
        env["DRY_RUN"] = "1"

        # The run for v1.9.0 finishes after v1.10.0 already moved v1.
        completed = subprocess.run(
            ["bash", str(SCRIPT_PATH), "v1", "v1.", commit_v1_9],
            cwd=repo_path,
            env=env,
            capture_output=True,
            text=True,
        )

        assert completed.returncode == 0
        assert "Not moving v1 back to v1.9.0: v1.10.0" in completed.stdout
        floating_target = subprocess.check_output(
            ["git", "rev-parse", "v1^{commit}"], cwd=repo_path, text=True
        ).strip()
        assert floating_target == commit_v1_10

        # The newest tag's own run still moves it.
        _run(["bash", str(SCRIPT_PATH), "v1", "v1.", commit_v1_10], cwd=repo_path, env=env)
        floating_target = subprocess.check_output(
            ["git", "rev-parse", "v1^{commit}"], cwd=repo_path, text=True
        ).strip()
        assert floating_target == commit_v1_10
