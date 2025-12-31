import textwrap

import pytest
import yaml

from scripts import ledger_migrate_base


def _write_ledger(path, data) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_detect_default_branch_explicit_override() -> None:
    assert ledger_migrate_base.detect_default_branch(" main ") == "main"
    with pytest.raises(ledger_migrate_base.MigrationError):
        ledger_migrate_base.detect_default_branch("   ")


def test_detect_default_branch_from_remote_show(monkeypatch) -> None:
    def fake_run(args):
        assert args == ["remote", "show", "origin"]
        return "  HEAD branch: trunk\n"

    monkeypatch.setattr(ledger_migrate_base, "_run_git", fake_run)
    assert ledger_migrate_base.detect_default_branch() == "trunk"


def test_detect_default_branch_from_symbolic_ref_origin(monkeypatch) -> None:
    def fake_run(args):
        if args == ["remote", "show", "origin"]:
            raise ledger_migrate_base.MigrationError("no remote")
        if args == ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]:
            return "refs/remotes/origin/main\n"
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(ledger_migrate_base, "_run_git", fake_run)
    assert ledger_migrate_base.detect_default_branch() == "main"


def test_detect_default_branch_falls_back_to_head(monkeypatch) -> None:
    def fake_run(args):
        if args == ["remote", "show", "origin"]:
            raise ledger_migrate_base.MigrationError("no remote")
        if args == ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"]:
            raise ledger_migrate_base.MigrationError("no origin head")
        if args == ["rev-parse", "--abbrev-ref", "origin/HEAD"]:
            return "origin/HEAD\n"
        if args == ["symbolic-ref", "--quiet", "HEAD"]:
            return "refs/heads/release\n"
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(ledger_migrate_base, "_run_git", fake_run)
    assert ledger_migrate_base.detect_default_branch() == "release"


def test_detect_default_branch_requires_fallback(monkeypatch) -> None:
    def fake_run(args):
        raise ledger_migrate_base.MigrationError(f"no git for {args}")

    monkeypatch.setattr(ledger_migrate_base, "_run_git", fake_run)
    with pytest.raises(ledger_migrate_base.MigrationError, match="unable to determine default"):
        ledger_migrate_base.detect_default_branch()


def test_load_ledger_requires_mapping(tmp_path) -> None:
    ledger_path = tmp_path / "issue-1-ledger.yml"
    ledger_path.write_text("- item\n", encoding="utf-8")
    with pytest.raises(ledger_migrate_base.MigrationError, match="ledger must be a mapping"):
        ledger_migrate_base.load_ledger(ledger_path)


def test_migrate_ledger_updates_when_needed(tmp_path) -> None:
    ledger_path = tmp_path / "issue-2-ledger.yml"
    _write_ledger(ledger_path, {"base": "develop", "items": ["one"]})

    result = ledger_migrate_base.migrate_ledger(ledger_path, "main", check=False)

    assert result.changed is True
    assert result.previous == "develop"
    assert result.updated == "main"
    assert yaml.safe_load(ledger_path.read_text(encoding="utf-8"))["base"] == "main"


def test_migrate_ledger_check_mode_does_not_write(tmp_path) -> None:
    ledger_path = tmp_path / "issue-3-ledger.yml"
    _write_ledger(ledger_path, {"base": "develop"})

    result = ledger_migrate_base.migrate_ledger(ledger_path, "main", check=True)

    assert result.changed is False
    assert result.updated is None
    assert yaml.safe_load(ledger_path.read_text(encoding="utf-8"))["base"] == "develop"


def test_migrate_ledger_noop_when_matching(tmp_path) -> None:
    ledger_path = tmp_path / "issue-4-ledger.yml"
    _write_ledger(ledger_path, {"base": "main"})

    result = ledger_migrate_base.migrate_ledger(ledger_path, "main", check=True)

    assert result.changed is False
    assert result.updated == "main"


def test_find_repo_root_wraps_git_failure(monkeypatch) -> None:
    def fake_run(args):
        raise ledger_migrate_base.MigrationError("no git")

    monkeypatch.setattr(ledger_migrate_base, "_run_git", fake_run)
    with pytest.raises(ledger_migrate_base.MigrationError, match="not inside a git repository"):
        ledger_migrate_base.find_repo_root()


def test_discover_ledgers_lists_agents(tmp_path) -> None:
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    first = agents_dir / "issue-1-ledger.yml"
    second = agents_dir / "issue-2-ledger.yml"
    first.write_text("base: main\n", encoding="utf-8")
    second.write_text("base: main\n", encoding="utf-8")

    assert ledger_migrate_base.discover_ledgers(tmp_path) == [first, second]


def test_main_reports_no_ledgers(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(ledger_migrate_base, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ledger_migrate_base, "detect_default_branch", lambda _=None: "main")
    monkeypatch.setattr(ledger_migrate_base, "discover_ledgers", lambda _root: [])

    assert ledger_migrate_base.main([]) == 0
    out = capsys.readouterr().out
    assert "No ledgers found" in out


def test_main_check_reports_mismatches(monkeypatch, capsys, tmp_path) -> None:
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    ledger_path = agents_dir / "issue-9-ledger.yml"
    ledger_path.write_text(
        textwrap.dedent(
            """\
        base: develop
        items: []
        """
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(ledger_migrate_base, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(ledger_migrate_base, "detect_default_branch", lambda _=None: "main")

    exit_code = ledger_migrate_base.main(["--check"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "Found ledgers with stale base values" in out
    assert str(ledger_path) in out


def test_main_emits_error_on_detection_failure(monkeypatch, capsys) -> None:
    def fail_root():
        raise ledger_migrate_base.MigrationError("boom")

    monkeypatch.setattr(ledger_migrate_base, "find_repo_root", fail_root)

    exit_code = ledger_migrate_base.main([])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "::error::boom" in err
