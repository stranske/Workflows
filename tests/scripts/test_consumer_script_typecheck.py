from __future__ import annotations

from pathlib import Path

from mypy import api as mypy_api

ROOT = Path(__file__).resolve().parents[2]


def test_manifest_synced_docs_helpers_typecheck_without_repo_overrides(tmp_path: Path) -> None:
    """Keep consumer-delivered helpers clean under a consumer mypy run."""
    config = tmp_path / "mypy.ini"
    config.write_text("[mypy]\n", encoding="utf-8")

    stdout, stderr, status = mypy_api.run(
        [
            "--config-file",
            str(config),
            "--cache-dir",
            str(tmp_path / "mypy-cache"),
            str(ROOT / "scripts/check_docs_drift.py"),
            str(ROOT / "scripts/sync_status_file_ignores.py"),
        ]
    )

    assert status == 0, stdout + stderr
