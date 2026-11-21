from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / ".github/scripts/publish_branch_snapshot_pointer.py"
SPEC = importlib.util.spec_from_file_location("publish_branch_snapshot_pointer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


@pytest.fixture
def runner(tmp_path: Path) -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": "stranske/Workflows",
        "GITHUB_REPOSITORY_ID": "1117447156",
        "GITHUB_WORKFLOW_REF": f"stranske/Workflows/{publisher.DIRECT}@refs/pull/4806/merge",
        "GITHUB_WORKFLOW_SHA": "f" * 40,
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_RUN_ID": "44877506358",
        "GITHUB_RUN_ATTEMPT": "1",
        "SNAPSHOT_ARTIFACT_ID": "14696966847",
        "SNAPSHOT_ARTIFACT_DIGEST": "sha256:" + "a" * 64,
        "SNAPSHOT_HEAD_REPOSITORY": "stranske/Workflows",
        "SNAPSHOT_DIR": str(tmp_path / "gate-branch-protection"),
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "github-output"),
    }


def launch(env: dict[str, str]) -> str:
    return subprocess.check_output([sys.executable, "-B", str(SCRIPT)], env=env, text=True)


def test_native_direct_pointer_references_only_current_files(
    runner: dict[str, str], tmp_path: Path
) -> None:
    snapshots = Path(runner["SNAPSHOT_DIR"])
    (snapshots / "previous").mkdir(parents=True)
    (snapshots / "previous/enforcement.json").write_bytes(b"{}")
    contents = b'{"changes_applied": false}'
    (snapshots / "verification.json").write_bytes(contents)
    (snapshots / "health-summary.json").write_bytes(b"[]")

    assert "prepared for artifact 14696966847" in launch(runner)
    pointer = tmp_path / publisher.POINTER_FILENAME
    result = json.loads(pointer.read_bytes())
    assert result["run_id"] == 44877506358 and result["run_attempt"] == 1
    assert result["caller_workflow_ref"] == runner["GITHUB_WORKFLOW_REF"]
    assert result["workflow_sha"] == runner["GITHUB_WORKFLOW_SHA"]
    assert result["artifact"] == {
        "id": 14696966847,
        "sha256": "a" * 64,
        "name": "gate-branch-protection-44877506358",
    }
    assert result["files"] == {"verification.json": hashlib.sha256(contents).hexdigest()}
    assert Path(runner["GITHUB_OUTPUT"]).read_text() == "ready=true\n"
    assert not (snapshots / pointer.name).exists()


def test_local_health40_call_preserves_separate_caller_and_attempt(
    runner: dict[str, str], tmp_path: Path
) -> None:
    snapshots = Path(runner["SNAPSHOT_DIR"])
    snapshots.mkdir()
    (snapshots / "verification.json").write_bytes(b'{"changes_applied": false}')
    (snapshots / "enforcement.json").write_bytes(b'{"changes_applied": true}')
    runner.update(
        GITHUB_WORKFLOW_REF=f"stranske/Workflows/{publisher.SWEEP}@refs/heads/main",
        GITHUB_EVENT_NAME="schedule",
        GITHUB_RUN_ID="43808942934",
        GITHUB_RUN_ATTEMPT="2",
        SNAPSHOT_ARTIFACT_ID="20",
        SNAPSHOT_ARTIFACT_DIGEST="b" * 64,
        SNAPSHOT_HEAD_REPOSITORY="",
    )
    pointer = publisher.build_pointer(runner, snapshots)
    assert pointer["producer_workflow"] == publisher.DIRECT
    assert pointer["caller_workflow_ref"] == runner["GITHUB_WORKFLOW_REF"]
    assert pointer["workflow_sha"] == runner["GITHUB_WORKFLOW_SHA"]
    assert pointer["run_attempt"] == 2
    assert pointer["artifact"]["name"] == "gate-branch-protection-43808942934"
    assert set(pointer["files"]) == {"verification.json", "enforcement.json"}
    # A rerun of the same source does not automatically carry authority.
    runner["SNAPSHOT_ARTIFACT_ID"] = ""
    assert "Snapshot pointer skipped" in launch(runner)
    assert not (tmp_path / publisher.POINTER_FILENAME).exists()


@pytest.mark.parametrize(
    ("override", "has_snapshot"),
    [
        ({"SNAPSHOT_HEAD_REPOSITORY": "different-owner/Workflows"}, True),
        (
            {
                "GITHUB_WORKFLOW_REF": "stranske/Workflows/.github/workflows/other.yml@refs/heads/main"
            },
            True,
        ),
        ({"GITHUB_WORKFLOW_REF": f"stranske/Workflows/{publisher.DIRECT}@refs/heads/trial"}, True),
        ({"SNAPSHOT_ARTIFACT_DIGEST": ""}, True),
        ({}, False),
    ],
    ids=["fork", "other-workflow", "untrusted-ref", "missing-digest", "summary-only"],
)
def test_pointer_skips_unqualified_native_result(
    runner: dict[str, str], tmp_path: Path, override: dict[str, str], has_snapshot: bool
) -> None:
    snapshots = Path(runner["SNAPSHOT_DIR"])
    snapshots.mkdir()
    (snapshots / "health-summary.json").write_bytes(b"[]")
    if has_snapshot:
        (snapshots / "verification.json").write_bytes(b"{}")
    runner.update(override)
    assert "Snapshot pointer skipped" in launch(runner)
    assert not Path(runner["GITHUB_OUTPUT"]).exists()
    assert not (tmp_path / publisher.POINTER_FILENAME).exists()


def test_fresh_rerun_keeps_the_lookup_name_but_changes_source_identity(
    runner: dict[str, str], tmp_path: Path
) -> None:
    snapshots = Path(runner["SNAPSHOT_DIR"])
    snapshots.mkdir()
    (snapshots / "verification.json").write_bytes(b'{"changes_applied": false}')
    assert "prepared for artifact 14696966847" in launch(runner)
    pointer_path = tmp_path / publisher.POINTER_FILENAME
    first = json.loads(pointer_path.read_text())

    runner.update(
        GITHUB_RUN_ATTEMPT="2",
        SNAPSHOT_ARTIFACT_ID="14696966848",
        SNAPSHOT_ARTIFACT_DIGEST="b" * 64,
        GITHUB_OUTPUT=str(tmp_path / "rerun-output"),
    )
    assert "prepared for artifact 14696966848" in launch(runner)
    second = json.loads(pointer_path.read_text())
    assert second["run_id"] == first["run_id"]
    assert second["run_attempt"] == 2
    assert second["artifact"]["name"] == first["artifact"]["name"]
    assert second["artifact"]["id"] != first["artifact"]["id"]
    assert second["artifact"]["sha256"] == "b" * 64

    workflow = SCRIPT.parent.parent / "workflows/health-44-gate-branch-protection.yml"
    old_upload, pointer_upload = workflow.read_text().split(
        "      - name: Publish snapshot pointer\n"
    )
    assert "overwrite:" not in old_upload
    assert "name: health44-snapshot-pointer-v1" in pointer_upload
    assert "overwrite: true" in pointer_upload
