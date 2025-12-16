from __future__ import annotations

import runpy
import sys
import zipfile
from pathlib import Path
from typing import Iterable

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
    (inner / "snap.json").write_text("{}", encoding="utf-8")
    (inner / "ignore.txt").write_text("ignored", encoding="utf-8")
    (inner / "nested.json").mkdir()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(inner / "snap.json", arcname="bundle/snap.json")
        zf.write(inner / "ignore.txt", arcname="bundle/ignore.txt")
        zf.write(inner / "nested.json", arcname="bundle/nested.json")

    target = tmp_path / "dest"
    rbs._extract_zip(archive, target)

    extracted = target / "bundle"
    assert (extracted / "snap.json").exists()
    assert (extracted / "ignore.txt").exists()

    destination = tmp_path / "previous"
    rbs._copy_json(extracted, destination)
    assert (destination / "snap.json").exists()
    assert not (destination / "ignore.txt").exists()


def test_copy_json_requires_content(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "dest"
    with pytest.raises(rbs.RestoreError):
        rbs._copy_json(source, destination)


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
        (target / "snapshot.json").write_text("{}", encoding="utf-8")

    def fake_copy(source, destination):
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "snapshot.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(rbs, "_download_artifact", fake_download)
    monkeypatch.setattr(rbs, "_extract_zip", fake_extract)
    monkeypatch.setattr(rbs, "_copy_json", fake_copy)

    restored = rbs.restore_previous_snapshots(
        repo="owner/repo",
        token="token",
        snapshot_dir=snapshot_dir,
        run_id="101",
    )

    assert restored is True
    previous_dir = snapshot_dir / "previous"
    assert (previous_dir / "snapshot.json").exists()


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
    monkeypatch.setattr(rbs, "_copy_json", lambda source, dest: None)

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
    exc_type, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    monkeypatch.setattr(rbs, "restore_previous_snapshots", lambda **kwargs: True)

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "restored previous snapshots" in captured.out.lower()


def test_main_reports_no_artifact(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("TARGET_REPO", "owner/repo")
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("SNAPSHOT_DIR", str(tmp_path / "snapshots"))
    monkeypatch.setattr(rbs, "restore_previous_snapshots", lambda **kwargs: False)

    result = rbs.main()

    captured = capsys.readouterr()
    assert result == 0
    assert "no previous artifact" in captured.out.lower()


def test_module_entrypoint_triggers_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGET_REPO", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(SCRIPT_DIR / "restore_branch_snapshots.py", run_name="__main__")

    assert exc.value.code == 0
