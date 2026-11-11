from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[3] / ".github" / "scripts" / "resolve_alert_issue.py"
# Loaded by path (not `import`) so the helper is not mistaken for a third-party
# test dependency by scripts/sync_test_dependencies.py.
_spec = importlib.util.spec_from_file_location("resolve_alert_issue", SCRIPT_PATH)
rai = importlib.util.module_from_spec(_spec)
sys.modules["resolve_alert_issue"] = rai
_spec.loader.exec_module(rai)

ALERT = "🚨 Consumer Repo Sync Failed - Action Required"


class FakeGh:
    def __init__(self, issues: list[dict], fail_on: str | None = None) -> None:
        self.issues = issues
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    def __call__(self, args):
        args = list(args)
        self.calls.append(args)
        if self.fail_on and args[1] == self.fail_on:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="boom")
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        return ""

    @property
    def closes(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["issue", "close"]]


ARGS = ["--repo", "o/r", "--label", "sync-failure", "--label", "automated", "--title", ALERT]


def test_closes_only_matching_title_not_other_producer_with_shared_labels(capsys):
    gh = FakeGh(
        [
            {"number": 7, "title": ALERT},
            {"number": 8, "title": "⏰ Consumer Repo Sync - Stale"},
        ]
    )
    assert rai.main([*ARGS, "--run-url", "https://x/run/1"], run=gh) == 0
    assert [c[2] for c in gh.closes] == ["7"]
    close = gh.closes[0]
    assert close[close.index("--reason") + 1] == "completed"
    assert "https://x/run/1" in close[close.index("--comment") + 1]
    assert "closed #7" in capsys.readouterr().out


def test_lists_with_every_label_so_label_sharing_issues_are_prefiltered():
    gh = FakeGh([])
    rai.main(ARGS, run=gh)
    listing = gh.calls[0]
    assert listing.count("--label") == 2
    assert "sync-failure" in listing and "automated" in listing


def test_noop_when_no_alert_is_open(capsys):
    gh = FakeGh([])
    assert rai.main(ARGS, run=gh) == 0
    assert gh.closes == []
    assert "nothing to close" in capsys.readouterr().out


def test_title_prefix_matches_variable_titles():
    gh = FakeGh([{"number": 3, "title": "⚠️ CODEX_AUTH_JSON expires in 9 hours"}])
    rai.main(
        ["--repo", "o/r", "--label", "auth-expiring", "--title-prefix", "⚠️ CODEX_AUTH_JSON"],
        run=gh,
    )
    assert [c[2] for c in gh.closes] == ["3"]


def test_gh_error_returns_nonzero_and_closes_nothing(capsys):
    gh = FakeGh([{"number": 7, "title": ALERT}], fail_on="close")
    assert rai.main(ARGS, run=gh) == 1
    assert "alert resolution failed" in capsys.readouterr().err


def test_requires_label_and_title():
    with pytest.raises(ValueError):
        rai.resolve_alerts(repo="o/r", labels=[], titles=["t"], run=FakeGh([]))
    with pytest.raises(ValueError):
        rai.resolve_alerts(repo="o/r", labels=["l"], run=FakeGh([]))
    with pytest.raises(SystemExit):
        rai.main(["--repo", "o/r", "--label", "l"], run=FakeGh([]))
