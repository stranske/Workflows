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
