"""End-to-end safety tests for scripts/sync_templates.sh."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]


def _fixture_repo(tmp_path: Path, manifest: str) -> Path:
    (tmp_path / "scripts").mkdir()
    for name in (
        "sync_templates.sh",
        "validate_template_sync.py",
        "sync_manifest_compiler.py",
    ):
        shutil.copy(REPO_ROOT / "scripts" / name, tmp_path / "scripts" / name)
    (tmp_path / ".github" / "scripts").mkdir(parents=True)
    (tmp_path / ".github" / "sync-manifest.yml").write_text(manifest, encoding="utf-8")
    template_root = tmp_path / "templates" / "consumer-repo"
    template_root.mkdir(parents=True)
    (template_root / "sentinel.txt").write_text("keep", encoding="utf-8")
    return tmp_path


def _run_sync(repo: Path) -> subprocess.CompletedProcess[str]:
    test_bin = repo / ".test-bin"
    test_bin.mkdir(exist_ok=True)
    python = test_bin / "python"
    if not python.exists():
        python.symlink_to(sys.executable)
    env = os.environ.copy()
    env["PATH"] = f"{test_bin}:{env['PATH']}"
    return subprocess.run(
        ["/bin/bash", "scripts/sync_templates.sh"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_sync_templates_rejects_manifest_source_escape(tmp_path: Path) -> None:
    source_name = f"outside-source-{tmp_path.name}"
    repo = _fixture_repo(
        tmp_path,
        f"""version: 1
scripts:
  - source: .github/scripts/../../../{source_name}
    description: traversal
    template_sync: exact
""",
    )
    unsafe_source = repo.parent / source_name
    unsafe_source.mkdir()
    (unsafe_source / "replacement.txt").write_text("replacement", encoding="utf-8")
    protected_destination = repo / "templates" / source_name
    protected_destination.mkdir()
    protected_sentinel = protected_destination / "protected.txt"
    protected_sentinel.write_text("protect", encoding="utf-8")
    before = (repo / "templates" / "consumer-repo" / "sentinel.txt").read_bytes()

    result = _run_sync(repo)

    assert result.returncode != 0
    assert "Manifest is invalid" in result.stderr
    assert (repo / "templates" / "consumer-repo" / "sentinel.txt").read_bytes() == before
    assert protected_sentinel.read_text(encoding="utf-8") == "protect"
    assert "All files already in sync" not in result.stdout


def test_sync_templates_rejects_destination_symlink(tmp_path: Path) -> None:
    repo = _fixture_repo(
        tmp_path,
        """version: 1
scripts:
  - source: .github/scripts/x.js
    description: test
""",
    )
    (repo / ".github" / "scripts" / "x.js").write_text("new", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_sentinel = outside / "x.js"
    outside_sentinel.write_text("outside", encoding="utf-8")
    destination_parent = repo / "templates" / "consumer-repo" / ".github"
    destination_parent.mkdir()
    (destination_parent / "scripts").symlink_to(outside, target_is_directory=True)

    result = _run_sync(repo)

    assert result.returncode != 0
    assert "symlink component is not allowed" in result.stderr
    assert outside_sentinel.read_text(encoding="utf-8") == "outside"


def test_sync_templates_syncs_manifest_script(tmp_path: Path) -> None:
    repo = _fixture_repo(
        tmp_path,
        """version: 1
scripts:
  - source: .github/scripts/new script.js
    description: test
""",
    )
    source = repo / ".github" / "scripts" / "new script.js"
    source.write_text("console.log('safe');\n", encoding="utf-8")

    result = _run_sync(repo)

    assert result.returncode == 0, result.stderr
    destination = repo / "templates" / "consumer-repo" / ".github" / "scripts" / "new script.js"
    assert destination.read_bytes() == source.read_bytes()
    assert (repo / "templates" / "consumer-repo" / "sentinel.txt").read_text() == "keep"

    second = _run_sync(repo)
    assert second.returncode == 0, second.stderr
    assert "✅ All files already in sync" in second.stdout
