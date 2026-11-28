from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = Path("scripts/consumer_sync/sync_test_helpers.sh")


@pytest.mark.skipif(shutil.which("bash") is None, reason="requires Bash")
@pytest.mark.parametrize("mode", ["check", "install"])
@pytest.mark.parametrize("existing_receiver", [False, True], ids=["fresh", "existing"])
def test_empty_helper_source_fails_without_destination_changes(
    tmp_path: Path, mode: str, existing_receiver: bool
) -> None:
    script = tmp_path / INSTALLER
    script.parent.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / INSTALLER, script)
    templates = tmp_path / "templates/test_helpers"
    templates.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "templates/test_helpers/README.md", templates / "README.md")
    (templates / "directory.py").mkdir()

    target = tmp_path / "receiver"
    target.mkdir()
    helper_dir = target / "tests/helpers"
    if existing_receiver:
        helper_dir.mkdir(parents=True)
        (helper_dir / "version_utils.py").write_bytes(b"# customized receiver helper\n")

    command = ["bash", INSTALLER.as_posix(), "--repo", "receiver"]
    if mode == "check":
        command.append("--check")
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)

    assert result.returncode == 1
    assert "No Python test helpers found" in result.stderr
    if existing_receiver:
        assert sorted(p.name for p in helper_dir.iterdir()) == ["version_utils.py"]
        assert (helper_dir / "version_utils.py").read_bytes() == b"# customized receiver helper\n"
    else:
        assert not (target / "tests").exists()
