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


# --- workflow wiring contract -------------------------------------------------

import yaml  # noqa: E402

WORKFLOWS = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _steps_calling_helper(job: dict) -> list[dict]:
    return [s for s in job.get("steps", []) if "resolve_alert_issue.py" in s.get("run", "")]


@pytest.mark.parametrize(
    ("workflow", "job", "label"),
    [
        ("maint-68-sync-consumer-repos.yml", "resolve-alert", "sync-failure"),
        ("health-71-sync-health-check.yml", "check-sync-health", "sync-failure"),
        ("health-67-integration-sync-check.yml", "check-sync", "integration-sync"),
        ("health-codex-auth-check.yml", None, "auth-expiring"),
    ],
)
def test_each_producer_closes_its_alert_on_a_gated_success_step(workflow, job, label):
    doc = _load(workflow)
    jobs = doc["jobs"]
    job_doc = jobs[job] if job else next(iter(jobs.values()))
    steps = _steps_calling_helper(job_doc)
    assert len(steps) == 1, f"{workflow} must call the shared helper exactly once"
    step = steps[0]
    assert step.get("continue-on-error") is True
    assert f"--label {label}" in step["run"]
    gate = str(step.get("if", "")) + str(job_doc.get("if", ""))
    assert any(tok in gate for tok in ("healthy", "== 'ok'", "success()", "'success'")), gate


def test_maint68_resolve_job_never_runs_for_failures_dry_runs_or_previews():
    job = _load("maint-68-sync-consumer-repos.yml")["jobs"]["resolve-alert"]
    cond = job["if"]
    for token in (
        "needs.prepare.result == 'success'",
        "needs.sync.result != 'failure'",
        "needs.validate.result != 'failure'",
        "inputs.dry_run != true",
        "!= 'preview'",
        "!cancelled()",
    ):
        assert token in cond
    assert set(job["needs"]) == {"prepare", "validate", "sync"}


def test_maint68_refused_dispatch_input_reports_refusal_instead_of_alerting():
    jobs = _load("maint-68-sync-consumer-repos.yml")["jobs"]
    assert "input_refusal == ''" in jobs["notify-failure"]["if"]
    assert "input_refusal != ''" in jobs["report-refusal"]["if"]
    assert "input_refusal" in jobs["prepare"]["outputs"]
    # the refusal path must not call gh issue create/comment
    run_text = " ".join(s.get("run", "") for s in jobs["report-refusal"]["steps"])
    assert "gh issue" not in run_text
