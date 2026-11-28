from scripts import cli_handler


def test_main_missing_token_exits_with_message(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ISSUE_DEDUP_SMOKE_ALLOWLIST", "owner/repo")
    monkeypatch.delenv("TEST_TOKEN", raising=False)

    result = cli_handler.main(
        [
            "--repo",
            "owner/repo",
            "--title",
            "Auth Test",
            "--token-env",
            "TEST_TOKEN",
            "--dry-run",
        ]
    )

    captured = capsys.readouterr()
    assert result == 1
    assert "Missing GitHub token in $TEST_TOKEN." in captured.err
