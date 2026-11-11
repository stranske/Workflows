"""scripts/campaign_plan_managed_paths.py: the managed path set Maint 71 uses to carry no-change evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
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

    def fake_build(source_root, expected_plan_id, source_commit, plan_scope, scope_base_sha):
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


def _fake_source_root(tmp_path: Path, plan: dict) -> Path:
    """A source checkout whose compiler and scoper are stand-ins; the scoper records its argv."""
    root = tmp_path / "source"
    (root / "scripts").mkdir(parents=True)
    (root / ".github").mkdir()
    (root / ".github" / "sync-manifest.yml").write_text("version: 1\n")
    (root / "scripts" / "sync_manifest_compiler.py").write_text(
        "import json, sys\n"
        "out = sys.argv[sys.argv.index('--output-json') + 1]\n"
        "json.dump({'schema': 'workflows.consumer-sync-plan/v1', 'plan_id': 'sha256:full',"
        " 'entries': [], 'removals': []}, open(out, 'w'))\n"
    )
    (root / "scripts" / "scope_consumer_sync_plan.py").write_text(
        "import json, sys\n"
        "json.dump(sys.argv[1:], open('scope-argv.json', 'w'))\n"
        "out = sys.argv[sys.argv.index('--output-json') + 1]\n"
        f"json.dump({plan!r}, open(out, 'w'))\n"
    )
    return root


def test_build_selects_the_plan_as_maint68_does_and_checks_its_identity(tmp_path: Path):
    plan = {
        "schema": "workflows.consumer-sync-plan/v1",
        "plan_id": "sha256:scoped",
        "entries": [{"target": ".github/workflows/pr-00-gate.yml", "requires": []}],
        "removals": [],
    }
    root = _fake_source_root(tmp_path, plan)
    doc, reason = cpmp.build(root, "sha256:scoped", "C" * 40, "source-delta", "b" * 40)
    assert reason == "ok"
    assert doc == {
        "schema": "workflows.consumer-sync-plan-managed-paths/v1",
        "plan_id": "sha256:scoped",
        "plan_scope": "source-delta",
        "source_commit": "c" * 40,
        "paths": [".github/workflows/pr-00-gate.yml", ".gitignore"],
        "directories": [],
    }
    argv = json.loads((root / "scope-argv.json").read_text())
    assert argv[argv.index("--mode") + 1] == "source-delta"
    assert argv[argv.index("--base-ref") + 1] == "b" * 40
    assert argv[argv.index("--head-ref") + 1] == "C" * 40


def test_build_refuses_a_mismatched_plan_id_or_an_unexpected_schema(tmp_path: Path):
    plan = {"schema": "workflows.consumer-sync-plan/v1", "plan_id": "sha256:other"}
    doc, reason = cpmp.build(_fake_source_root(tmp_path / "a", plan), "sha256:scoped", "c" * 40)
    assert doc is None
    assert reason == "selected plan sha256:other is not the expected sha256:scoped"
    wrong = {"schema": "something-else/v9", "plan_id": "sha256:scoped"}
    doc, reason = cpmp.build(_fake_source_root(tmp_path / "b", wrong), "sha256:scoped", "c" * 40)
    assert doc is None
    assert reason == "unexpected plan schema 'something-else/v9'"
    doc, reason = cpmp.build(tmp_path, "sha256:scoped", "c" * 40, "partial")
    assert reason == "unsupported plan scope 'partial'"


def test_managed_paths_refuses_entries_and_removals_without_a_target():
    with pytest.raises(ValueError, match="plan entry without a target"):
        cpmp.managed_paths({"entries": [{"target": " ", "requires": []}]})
    with pytest.raises(ValueError, match="plan removal without a target"):
        cpmp.managed_paths({"entries": [], "removals": [{"target": ""}]})


def test_build_refuses_when_the_scoper_fails(tmp_path: Path):
    root = _fake_source_root(
        tmp_path, {"schema": "workflows.consumer-sync-plan/v1", "is_directory": True}
    )
    (root / "scripts" / "scope_consumer_sync_plan.py").write_text("raise SystemExit(2)\n")
    doc, reason = cpmp.build(root, "sha256:scoped", "c" * 40, "source-delta", "b" * 40)
    assert doc is None
    assert reason.startswith("plan scope failed:")


def test_main_forwards_scope_arguments(tmp_path: Path, monkeypatch):
    seen = {}

    def fake_build(*args):
        seen["args"] = args
        return None, "stop"

    monkeypatch.setattr(cpmp, "build", fake_build)
    rc = cpmp.main(
        [
            *_args(tmp_path, "sha256:p", tmp_path / "o.json"),
            "--plan-scope",
            "source-delta",
            "--scope-base-sha",
            "b" * 40,
        ]
    )
    assert rc == 0
    assert seen["args"][3:] == ("source-delta", "b" * 40)
