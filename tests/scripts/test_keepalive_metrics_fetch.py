from __future__ import annotations

import zipfile
from pathlib import Path

from scripts import keepalive_metrics_fetch as fetch


def test_parse_repo_list_handles_csv_and_json() -> None:
    assert fetch._parse_repo_list("org/repo, other/repo") == ["org/repo", "other/repo"]
    assert fetch._parse_repo_list('["org/repo", "other/repo"]') == ["org/repo", "other/repo"]


def test_apply_repo_filter_preserves_order() -> None:
    repos = ["Org/One", "org/two", "org/three"]
    filtered = fetch._apply_repo_filter(repos, "org/two,org/one")
    assert filtered == ["Org/One", "org/two"]


def test_select_artifacts_prefers_latest() -> None:
    artifacts = [
        {"id": 1, "name": "keepalive-metrics", "expired": False, "created_at": "2024-01-01"},
        {"id": 2, "name": "keepalive-metrics", "expired": False, "created_at": "2024-02-01"},
        {"id": 3, "name": "other", "expired": False, "created_at": "2024-03-01"},
    ]
    selected = fetch._select_artifacts(artifacts, "keepalive-metrics", 1)
    assert [item["id"] for item in selected] == [2]


def test_extract_metrics_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "artifact.zip"
    metrics_name = "keepalive-metrics.ndjson"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(f"nested/{metrics_name}", '{"ok": true}')

    output_dir = tmp_path / "out"
    extracted = fetch._extract_metrics_zip(zip_path, output_dir, metrics_name)

    assert extracted is True
    assert (output_dir / metrics_name).exists()
