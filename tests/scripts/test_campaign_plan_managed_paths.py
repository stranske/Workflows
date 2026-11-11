"""scripts/campaign_plan_managed_paths.py: the managed path set Maint 71 uses to carry no-change evidence."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import campaign_plan_managed_paths as cpmp


def test_managed_paths_cover_targets_directories_removals_requires_and_gitignore():
    plan = {
        "entries": [
            {"target": ".github/workflows/pr-00-gate.yml", "is_directory": False, "requires": []},
            {
                "target": "scripts/runner_lib/",
                "is_directory": True,
                "requires": ["tools/requirements-llm.txt"],
            },
        ],
        "removals": [{"target": ".github/workflows/dependabot-automerge.yml"}],
    }
    got = cpmp.managed_paths(plan)
    assert got["paths"] == [
        ".github/workflows/dependabot-automerge.yml",
        ".github/workflows/pr-00-gate.yml",
        ".gitignore",
        "tools/requirements-llm.txt",
    ]
    assert got["directories"] == [
        ".github/workflows/dependabot-automerge.yml",
        "scripts/runner_lib",
    ]


def _args(tmp_path: Path, plan_id: str, out: Path) -> list[str]:
    return [
        "--source-root",
        str(tmp_path),
        "--expected-plan-id",
        plan_id,
        "--source-commit",
        "c" * 40,
        "--output",
        str(out),
    ]


def test_a_plan_id_mismatch_or_compile_failure_writes_nothing(tmp_path: Path, monkeypatch):
    out = tmp_path / "managed.json"

    def fake_build(source_root, expected_plan_id, source_commit):
        return None, "compiled plan sha256:a is not the expected sha256:b"

    monkeypatch.setattr(cpmp, "build", fake_build)
    rc = cpmp.main(_args(tmp_path, "sha256:b", out))
    assert rc == 0
    assert out.exists() is False
    # A source root with no compiler fails closed too (no file, exit 0).
    monkeypatch.undo()
    rc = cpmp.main(_args(tmp_path, "sha256:b", out))
    assert rc == 0
    assert out.exists() is False


def test_a_matching_plan_is_written_with_its_identity(tmp_path: Path, monkeypatch):
    out = tmp_path / "managed.json"
    doc = {
        "schema": cpmp.SCHEMA,
        "plan_id": "sha256:p",
        "source_commit": "c" * 40,
        "paths": [".gitignore"],
        "directories": [],
    }
    monkeypatch.setattr(cpmp, "build", lambda *a: (doc, "ok"))
    rc = cpmp.main(_args(tmp_path, "sha256:p", out))
    assert rc == 0
    written = json.loads(out.read_text())
    assert written["schema"] == "workflows.consumer-sync-plan-managed-paths/v1"
    assert written["plan_id"] == "sha256:p"
    assert written["paths"] == [".gitignore"]
