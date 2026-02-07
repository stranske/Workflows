import subprocess

import scripts.ledger_validate as ledger_validate


def test_fetch_commit_uses_second_remote_after_origin_failure(monkeypatch) -> None:
    commit = "abc1234"
    base_url = "https://github.example.com/owner/repo.git"

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.example.com")

    calls: list[list[str]] = []

    def fake_check_call(command: list[str], stdout=None, stderr=None) -> None:
        calls.append(command)
        if "origin" in command:
            raise subprocess.CalledProcessError(1, command)
        if base_url in command:
            return None
        raise AssertionError(f"Unexpected fetch target in {command}")

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit(commit) is True

    origin_index = next(i for i, cmd in enumerate(calls) if "origin" in cmd)
    base_index = next(i for i, cmd in enumerate(calls) if base_url in cmd)
    assert origin_index < base_index


def test_fetch_commit_all_remotes_fail(monkeypatch) -> None:
    commit = "abc1234"
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.example.com")

    calls: list[list[str]] = []

    def fake_check_call(command: list[str], stdout=None, stderr=None) -> None:
        calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit(commit) is False
    assert len(calls) == 6


def test_fetch_commit_retry_then_succeeds(monkeypatch) -> None:
    commit = "abc1234"
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

    calls: list[list[str]] = []

    def fake_check_call(command: list[str], stdout=None, stderr=None) -> None:
        calls.append(command)
        if len(calls) < 3:
            raise subprocess.CalledProcessError(1, command)
        return None

    monkeypatch.setattr(ledger_validate.subprocess, "check_call", fake_check_call)

    assert ledger_validate._fetch_commit(commit) is True
    assert len(calls) == 4
    assert commit in calls[-1]
