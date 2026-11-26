from __future__ import annotations

import runpy
import subprocess
import sys
import textwrap
import zipfile
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path

import pytest

# Add script directory to path before importing restore_branch_snapshots
SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".github" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import restore_branch_snapshots as rbs  # noqa: E402


class DummyResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: dict | None = None,
        text: str = "",
        links: dict | None = None,
        chunks: Iterable[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.links = links or {}
        self._chunks = list(chunks or [b"data"])

    def json(self) -> dict:
        return self._json_data

    def iter_content(self, chunk_size: int) -> Iterable[bytes]:
        yield from self._chunks


class DummySession:
    def __init__(self, responses: list[DummyResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict, float, bool]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict,
        timeout: float,
        stream: bool = False,
    ) -> DummyResponse:
        self.calls.append((url, headers, timeout, stream))
        if not self._responses:
            raise AssertionError("Unexpected request")
        return self._responses.pop(0)


def test_iter_artifacts_filters_invalid_entries() -> None:
    response = {
        "artifacts": [
            {"id": "1", "name": "snap-A", "created_at": "2024", "expired": False},
            "not-a-dict",
            {"id": "invalid"},
            {"id": 2, "name": "snap-B", "created_at": "2023", "expired": True},
            {
                "id": 3,
                "name": "snap-C",
                "created_at": "2025",
                "expired": False,
                "workflow_run": {"id": "77"},
            },
        ]
    }

    artifacts = list(rbs._iter_artifacts(response))

    assert [art.id for art in artifacts] == [1, 2, 3]
    assert [art.workflow_run_id for art in artifacts] == [None, None, 77]


def test_iter_artifacts_handles_non_sequence_and_invalid_workflow() -> None:
    assert list(rbs._iter_artifacts({"artifacts": None})) == []

    artifacts = list(
        rbs._iter_artifacts(
            {
                "artifacts": [
                    {
                        "id": 4,
                        "name": "snap",
                        "created_at": "2024",
                        "expired": False,
                        "workflow_run": {"id": object()},
                    }
                ]
            }
        )
    )

    assert len(artifacts) == 1
    assert artifacts[0].workflow_run_id is None


def test_collect_artifacts_supports_pagination() -> None:
    responses = [
        DummyResponse(
            json_data={
                "artifacts": [
                    {
                        "id": 10,
                        "name": "snap-1",
                        "created_at": "2024-01-01",
                        "expired": False,
                    }
                ]
            },
            links={"next": {"url": "next-page"}},
        ),
        DummyResponse(
            json_data={
                "artifacts": [
                    {
                        "id": 20,
                        "name": "snap-2",
                        "created_at": "2024-01-02",
                        "expired": False,
                    }
                ]
            }
        ),
    ]
    session = DummySession(responses)

    artifacts = rbs._collect_artifacts(session, "owner/repo", "token")

    assert [art.id for art in artifacts] == [10, 20]
    assert session.calls[0][0].endswith("per_page=100")
    assert session.calls[0][3] is False  # not streaming when listing


def test_collect_artifacts_raises_on_http_error() -> None:
    session = DummySession(
        [DummyResponse(status_code=500, text="boom", json_data={"artifacts": []})]
    )

    with pytest.raises(rbs.RestoreError) as exc:
        rbs._collect_artifacts(session, "owner/repo", "token")

    assert "Failed to list artifacts" in str(exc.value)


def test_download_artifact_writes_chunks(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.zip"
    session = DummySession(
        [DummyResponse(chunks=[b"chunk1", b"", b"chunk2"], json_data={}, text="")]
    )

    rbs._download_artifact(session, "repo", "token", artifact_id=99, destination=destination)

    assert destination.read_bytes() == b"chunk1chunk2"
    url = session.calls[0][0]
    assert url.endswith("/actions/artifacts/99/zip")
    assert session.calls[0][3] is True


def test_download_artifact_raises_on_bad_status(tmp_path: Path) -> None:
    session = DummySession([DummyResponse(status_code=404, text="missing", json_data={})])

    with pytest.raises(rbs.RestoreError):
        rbs._download_artifact(session, "repo", "token", 1, tmp_path / "out.zip")


def test_extract_zip_and_copy_json(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "verification.json").write_text("{}", encoding="utf-8")
    (inner / "ignore.txt").write_text("ignored", encoding="utf-8")
    (inner / "nested.json").mkdir()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(inner / "verification.json", arcname="bundle/verification.json")
        zf.write(inner / "ignore.txt", arcname="bundle/ignore.txt")
        zf.write(inner / "nested.json", arcname="bundle/nested.json")

    target = tmp_path / "dest"
    rbs._extract_zip(archive, target)

    extracted = target / "bundle"
    assert (extracted / "verification.json").exists()
    assert (extracted / "ignore.txt").exists()

    destination = tmp_path / "previous"
    assert list(rbs._copy_json(extracted, destination)) == ["verification.json"]
    assert (destination / "verification.json").exists()
    assert not (destination / "ignore.txt").exists()


def test_copy_json_requires_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "dest"
    with pytest.raises(rbs.RestoreError):
        list(rbs._copy_json(source, destination))


def test_restore_previous_snapshots_happy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot_dir = tmp_path / "gate-branch-protection"
    snapshot_dir.mkdir()
    previous_dir = snapshot_dir / "previous"
    previous_dir.mkdir()
    (previous_dir / "old.json").write_text("{}", encoding="utf-8")

    artifacts = [
        rbs.Artifact(
            id=5,
            name="gate-branch-protection-123",
            created_at="2024-01-05T00:00:00Z",
            expired=False,
            workflow_run_id=99,
        )
    ]

    monkeypatch.setattr(rbs, "_collect_artifacts", lambda session, repo, token: artifacts)

    def fake_download(session, repo, token, artifact_id, destination):
        destination.write_bytes(b"dummy")

    def fake_extract(archive, target_dir):
        target = target_dir / snapshot_dir.name
        target.mkdir(parents=True, exist_ok=True)
        (target / "verification.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(rbs, "_download_artifact", fake_download)
    monkeypatch.setattr(rbs, "_extract_zip", fake_extract)

    restored = rbs.restore_previous_snapshots(
        repo="owner/repo",
        token="token",
        snapshot_dir=snapshot_dir,
        run_id="101",
    )

    assert restored is True
    previous_dir = snapshot_dir / "previous"
    assert (previous_dir / "verification.json").exists()


def test_restore_previous_snapshots_no_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot_dir = tmp_path / "gate"
    snapshot_dir.mkdir()

    monkeypatch.setattr(rbs, "_collect_artifacts", lambda session, repo, token: [])

    restored = rbs.restore_previous_snapshots(
        repo="owner/repo",
        token="token",
        snapshot_dir=snapshot_dir,
        run_id="101",
    )

    assert restored is False


def test_restore_previous_snapshots_missing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot_dir = tmp_path / "gate"
    snapshot_dir.mkdir()

    artifact = rbs.Artifact(
        id=5,
        name="gate-123",
        created_at="2024",
        expired=False,
        workflow_run_id=None,
    )

    monkeypatch.setattr(rbs, "_collect_artifacts", lambda session, repo, token: [artifact])
    monkeypatch.setattr(rbs, "_download_artifact", lambda *args, **kwargs: None)

    def fake_extract(archive, target_dir):
        (target_dir / "other").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(rbs, "_extract_zip", fake_extract)

    with pytest.raises(rbs.RestoreError):
        rbs.restore_previous_snapshots(
            repo="owner/repo",
            token="token",
            snapshot_dir=snapshot_dir,
            run_id="101",
        )


@pytest.mark.parametrize(
    "exc_type", [rbs.RestoreError("failed"), rbs.requests.RequestException("boom")]
)
def test_main_handles_restore_errors(
    exc_type, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    output = tmp_path / "step-output"
    output.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("TARGET_REPO", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("SNAPSHOT_DIR", "snapshots")
    monkeypatch.setattr(
        rbs,
        "restore_previous_snapshots",
        lambda **kwargs: (_ for _ in ()).throw(exc_type),
    )

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "snapshot" in captured.out.lower()
    assert output.read_text() == ""


def test_main_skips_when_missing_repo_or_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TARGET_REPO", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "missing repository or token" in captured.out.lower()


def test_main_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGET_REPO", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "step-output"))
    monkeypatch.setattr(rbs, "restore_previous_snapshots", lambda **kwargs: True)

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "restored previous snapshots" in captured.out.lower()
    assert (tmp_path / "step-output").read_text() == "lookup=complete\n"


def test_main_reports_no_artifact(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGET_REPO", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "step-output"))
    monkeypatch.setattr(rbs, "restore_previous_snapshots", lambda **kwargs: False)

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "no previous artifact" in captured.out.lower()
    assert (tmp_path / "step-output").read_text() == "lookup=complete\n"


def test_module_entrypoint_triggers_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_REPO", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    # Also clear fallback env vars so main() takes the early-return path
    # instead of making real API calls (GITHUB_REPOSITORY and GITHUB_TOKEN
    # are set in dev containers and CI).
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(SCRIPT_DIR / "restore_branch_snapshots.py", run_name="__main__")

    assert exc.value.code == 0


@pytest.mark.parametrize(
    ("restore_exit", "step_exit", "notice"),
    [
        (0, 0, ""),
        (124, 0, "[summary] Snapshot restore timed out; continuing without previous snapshots\n"),
        (42, 42, ""),
    ],
    ids=["success", "timeout", "unexpected-error"],
)
def test_workflow_restore_step_preserves_exit_status(
    tmp_path: Path, restore_exit: int, step_exit: int, notice: str
) -> None:
    workflow = SCRIPT_DIR.parent / "workflows" / "health-44-gate-branch-protection.yml"
    source = workflow.read_text(encoding="utf-8")
    name = "      - name: Restore previous branch protection snapshots\n"
    step = source.split(name, 1)[1].split("\n      - name: ", 1)[0]
    restore = textwrap.dedent(step.split("        run: |\n", 1)[1])
    timeout = tmp_path / "timeout"
    timeout.write_text(
        "#!/bin/sh\n"
        '[ "$*" = "5m python .github/scripts/restore_branch_snapshots.py" ] || exit 99\n'
        'exit "$FIXTURE_EXIT"\n',
        encoding="utf-8",
    )
    timeout.chmod(0o755)
    output = tmp_path / "step-output"
    output.touch()
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", restore],
        env={
            "PATH": str(tmp_path),
            "FIXTURE_EXIT": str(restore_exit),
            "GITHUB_OUTPUT": str(output),
        },
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == step_exit
    assert result.stdout == notice
    assert result.stderr == ""
    assert output.read_text() == ("lookup=timed_out\n" if restore_exit == 124 else "")


@pytest.mark.parametrize(
    ("layout", "archive_files", "available", "expired", "artifact_run", "expected"),
    [
        (
            "",
            {"verification.json": b'{"current": {}}', "health-summary.json": b"[]"},
            True,
            False,
            99,
            True,
        ),
        (
            "gate-branch-protection/",
            {"enforcement.json": b'{"current": {}}'},
            True,
            False,
            99,
            True,
        ),
        ("", {"health-summary.json": b"[]"}, True, False, 99, None),
        ("gate-branch-protection/", {"metadata.json": b"{}"}, True, False, 99, None),
        ("gate-branch-protection/", {"verification.json": b"{"}, True, False, 99, None),
        ("", {"verification.json": b"[]"}, True, False, 99, None),
        ("", {"verification.json": b'{"current": NaN}'}, True, False, 99, None),
        ("", {}, True, False, 99, None),
        ("", {"verification.json": b"{}"}, False, False, 99, None),
        ("", {"verification.json": b"{}"}, True, True, 99, False),
        ("", {"verification.json": b"{}"}, True, False, 101, False),
    ],
    ids=[
        "flat-verification",
        "nested-enforcement",
        "summary-only",
        "nested-metadata-only",
        "invalid-json",
        "invalid-protection-shape",
        "non-json-number",
        "bad-zip",
        "unavailable-download",
        "expired",
        "current-run",
    ],
)
def test_restore_snapshot_archive_preserves_usable_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    layout: str,
    archive_files: dict[str, bytes],
    available: bool,
    expired: bool,
    artifact_run: int,
    expected: bool | None,
) -> None:
    archive = BytesIO()
    if archive_files:
        with zipfile.ZipFile(archive, "w") as archive_writer:
            for name, contents in archive_files.items():
                archive_writer.writestr(layout + name, contents)
            archive_writer.writestr(layout + "previous/must-not-restore.json", b"{}")
    else:
        archive.write(b"partial transfer")
    response = DummyResponse(
        json_data={
            "artifacts": [
                {
                    "id": 5,
                    "name": f"gate-branch-protection-{artifact_run}",
                    "created_at": "2024-01-05T00:00:00Z",
                    "expired": expired,
                    "workflow_run": {"id": artifact_run},
                }
            ]
        }
    )
    downloader = DummyResponse(status_code=200 if available else 410, chunks=[archive.getvalue()])
    session = DummySession([response, downloader])
    monkeypatch.setattr(rbs.requests, "Session", lambda: session)
    snapshot_dir = tmp_path / "gate-branch-protection"
    previous = snapshot_dir / "previous"
    previous.mkdir(parents=True)
    (snapshot_dir / "verification.json").write_bytes(b'{"current": "current-check"}')
    old_snapshots = {
        "enforcement.json": b'{"current": "prior-enforce"}',
        "verification.json": b'{"current": "prior-check"}',
    }
    for name, contents in old_snapshots.items():
        (previous / name).write_bytes(contents)
    (previous / "keep.txt").write_bytes(b"notes")

    if expected is None:
        with pytest.raises(rbs.RestoreError):
            rbs.restore_previous_snapshots(
                repo="owner/repo", token="token", snapshot_dir=snapshot_dir, run_id="101"
            )
    else:
        restored = rbs.restore_previous_snapshots(
            repo="owner/repo", token="token", snapshot_dir=snapshot_dir, run_id="101"
        )
        assert restored is expected

    assert (snapshot_dir / "verification.json").read_bytes() == b'{"current": "current-check"}'
    assert (previous / "keep.txt").read_bytes() == b"notes"
    files = {path.name: path.read_bytes() for path in previous.glob("*.json")}
    if expected:
        assert files == old_snapshots | archive_files
        assert "Snapshot restore source: artifact 5, run 99" in capsys.readouterr().out
    else:
        assert files == old_snapshots
        if expected is False:
            assert len(session.calls) == 1


def test_restore_logs_each_committed_file_before_a_later_write_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot_dir = tmp_path / "gate"
    previous = snapshot_dir / "previous"
    previous.mkdir(parents=True)
    (previous / "verification.json").write_bytes(b'{"old": true}')

    archive_path = tmp_path / "artifact.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("enforcement.json", b'{"new": true}')
        archive.writestr("verification.json", b'{"new": true}')

    artifact = rbs.Artifact(5, "gate-99", "2026-01-01T00:00:00Z", False, 99)
    monkeypatch.setattr(rbs, "_collect_artifacts", lambda *args: [artifact])
    monkeypatch.setattr(
        rbs, "_download_artifact", lambda *args: args[-1].write_bytes(archive_path.read_bytes())
    )
    replace = Path.replace

    def fail_verification(source: Path, destination: Path) -> Path:
        if destination == previous / "verification.json":
            raise PermissionError("cannot replace verification")
        return replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_verification)
    with pytest.raises(PermissionError, match="cannot replace verification"):
        rbs.restore_previous_snapshots(
            repo="owner/repo", token="token", snapshot_dir=snapshot_dir, run_id="101"
        )

    assert (previous / "enforcement.json").read_bytes() == b'{"new": true}'
    assert (previous / "verification.json").read_bytes() == b'{"old": true}'
    notice = capsys.readouterr().out
    assert "artifact 5, run 99, file: enforcement.json" in notice
    assert "file: verification.json" not in notice
