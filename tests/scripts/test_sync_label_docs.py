from pathlib import Path

import pytest
from scripts import sync_label_docs


def test_default_source_is_the_consumer_specific_template() -> None:
    assert Path("templates/consumer-repo/docs/LABELS.md") == sync_label_docs.DEFAULT_SOURCE


def write_label_doc(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_source_unchanged_skips_cleanly(tmp_path: Path) -> None:
    source = tmp_path / "source" / "LABELS.md"
    checkout = tmp_path / "checkout"
    write_label_doc(source, "# Labels\n\nSame content\n")
    write_label_doc(checkout / "docs" / "LABELS.md", "# Labels\n\nSame content\n")

    commands: list[list[str]] = []

    def run(command: list[str], cwd: Path | None) -> None:
        commands.append(command)

    result = sync_label_docs.sync_checkout(
        repo="owner/repo",
        source_file=source,
        checkout_dir=checkout,
        run=run,
    )

    assert result.status == "skipped"
    assert result.message == "No changes needed for owner/repo"
    assert commands == []


def test_source_changed_writes_doc_and_pushes_commit(tmp_path: Path) -> None:
    source = tmp_path / "source" / "LABELS.md"
    checkout = tmp_path / "checkout"
    write_label_doc(source, "# Labels\n\nNew content\n")
    write_label_doc(checkout / "docs" / "LABELS.md", "# Labels\n\nOld content\n")

    commands: list[tuple[list[str], Path | None]] = []

    def run(command: list[str], cwd: Path | None) -> None:
        commands.append((command, cwd))

    result = sync_label_docs.sync_checkout(
        repo="owner/repo",
        source_file=source,
        checkout_dir=checkout,
        run=run,
    )

    assert result.status == "updated"
    assert (checkout / "docs" / "LABELS.md").read_text(encoding="utf-8") == (
        "# Labels\n\nNew content\n"
    )
    assert [command for command, _cwd in commands] == [
        ["git", "config", "user.name", "github-actions[bot]"],
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        ["git", "add", "docs/LABELS.md"],
        ["git", "commit", "-m", "docs: sync LABELS.md from Workflows repository"],
        ["git", "push"],
    ]
    assert all(cwd == checkout.resolve() for _command, cwd in commands)


def test_missing_target_docs_directory_fails_clearly(tmp_path: Path) -> None:
    source = tmp_path / "source" / "LABELS.md"
    checkout = tmp_path / "checkout"
    write_label_doc(source, "# Labels\n")
    checkout.mkdir()

    with pytest.raises(sync_label_docs.SyncLabelDocsError) as excinfo:
        sync_label_docs.sync_checkout(
            repo="owner/repo",
            source_file=source,
            checkout_dir=checkout,
        )

    assert "owner/repo: target docs directory not found: docs" in str(excinfo.value)


def test_helpers_hash_redact_and_parse_repositories(tmp_path: Path) -> None:
    document = tmp_path / "labels.md"
    document.write_text("labels", encoding="utf-8")

    assert sync_label_docs.parse_repos(" one/repo, ,two/repo ") == ["one/repo", "two/repo"]
    assert sync_label_docs.file_sha256(tmp_path / "missing") is None
    assert sync_label_docs.file_sha256(document) == sync_label_docs.file_sha256(document)
    assert (
        sync_label_docs.redact_command(["git", "push", "secret-token"], ["secret-token"])
        == "git push ***"
    )


def test_run_command_reports_redacted_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 1
        stderr = "bad credential"
        stdout = ""

    monkeypatch.setattr(sync_label_docs.subprocess, "run", lambda *args, **kwargs: Completed())

    with pytest.raises(sync_label_docs.SyncLabelDocsError) as excinfo:
        sync_label_docs.run_command(["git", "push", "secret-token"], redactions=["secret-token"])

    assert str(excinfo.value) == "git push *** failed with exit 1: bad credential"


def test_sync_repo_and_repos_handle_clone_and_member_failures(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    source.write_text("new", encoding="utf-8")
    commands: list[list[str]] = []

    def successful_run(command: list[str], cwd: Path | None) -> None:
        commands.append(command)
        if command[:2] == ["git", "clone"]:
            assert cwd is None
            clone_path = Path(command[-1])
            (clone_path / "docs").mkdir(parents=True)
            (clone_path / "docs" / "LABELS.md").write_text("old", encoding="utf-8")

    result = sync_label_docs.sync_repo(
        repo="owner/repo", token="a token/with symbols", source_file=source, run=successful_run
    )

    assert result.status == "updated"
    assert (
        commands[0][4]
        == "https://x-access-token:a%20token%2Fwith%20symbols@github.com/owner/repo.git"
    )

    def clone_failure(command: list[str], cwd: Path | None) -> None:
        raise sync_label_docs.SyncLabelDocsError("network unavailable")

    with pytest.raises(sync_label_docs.SyncLabelDocsError, match="owner/repo: clone failed"):
        sync_label_docs.sync_repo(
            repo="owner/repo", token="token", source_file=source, run=clone_failure
        )

    monkeypatch_results = [
        sync_label_docs.SyncResult("one/repo", "skipped", "unchanged"),
        sync_label_docs.SyncLabelDocsError("two/repo: failed"),
    ]

    def fake_sync_repo(**kwargs: object) -> sync_label_docs.SyncResult:
        result = monkeypatch_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    original = sync_label_docs.sync_repo
    sync_label_docs.sync_repo = fake_sync_repo  # type: ignore[assignment]
    try:
        with pytest.raises(sync_label_docs.SyncLabelDocsError, match="two/repo: failed"):
            sync_label_docs.sync_repos(repos=["one/repo", "two/repo"], token="token")
    finally:
        sync_label_docs.sync_repo = original  # type: ignore[assignment]


def test_main_validates_repositories_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["sync_label_docs.py", "--repos", "  "])
    with pytest.raises(SystemExit, match="No repositories supplied"):
        sync_label_docs.main()

    monkeypatch.setattr("sys.argv", ["sync_label_docs.py", "--repos", "owner/repo"])
    monkeypatch.delenv("SYNC_TOKEN", raising=False)
    with pytest.raises(SystemExit, match=r"Missing sync token in \$SYNC_TOKEN"):
        sync_label_docs.main()
