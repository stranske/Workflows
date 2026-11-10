from datetime import UTC, datetime, timedelta

from scripts import ci_time_budget as budget
from scripts import health85_followup as follow

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


def native_series(monkeypatch, *, bad_day=None):
    monkeypatch.setenv("GITHUB_REPOSITORY", budget.SOURCE_REPO)
    row = {}
    for offset in range(7):
        day = NOW - timedelta(days=6 - offset)
        monkeypatch.setenv("GITHUB_RUN_ID", str(1000 + offset))
        value = (
            None
            if offset == bad_day
            else {"p50": 8, "p90": 9, "longest_job": {}, "sample_count": 2}
        )
        row = budget.observation(row, value, day)
    return {budget.SOURCE_REPO: row}


def test_real_sources_survive_refresh_and_old_numeric_dates_never_qualify(monkeypatch):
    report = native_series(monkeypatch)
    row = report[budget.SOURCE_REPO]
    result = follow.evaluate(report, NOW)
    assert result["qualifying_seven_day_series"]
    assert len({r["source_run_url"] for r in result["observations"]}) == 7
    monkeypatch.delenv("GITHUB_RUN_ID")
    refreshed = budget.observation(row, {"p50": 9}, NOW)
    assert refreshed["daily_observations"] == row["daily_observations"]
    del row["daily_observations"]
    assert not follow.evaluate(report, NOW)["qualifying_seven_day_series"]


def test_missing_day_and_failed_measurement_do_not_authorize_network_writes(monkeypatch):
    report = native_series(monkeypatch, bad_day=3)

    class NoAPI:
        def __getattr__(self, name):
            raise AssertionError(f"incomplete evidence must not call {name}")

    result = follow.reconcile(NoAPI(), report, NOW)
    assert not result["completion_reconciled"]
    assert result["action"] == "retain_incomplete"
    row = report[budget.SOURCE_REPO]
    row["daily_observations"].pop("2026-11-05")
    assert not follow.evaluate(report, NOW)["qualifying_seven_day_series"]


def test_current_native_run_waits_for_its_final_conclusion(monkeypatch):
    report = native_series(monkeypatch)

    class NoAPI:
        def __getattr__(self, name):
            raise AssertionError(name)

    result = follow.reconcile(NoAPI(), report, NOW)
    assert "missing native dates: 2026-11-03" in result["budget"]["failures"]


def test_qualifying_sources_publish_once_then_observe_merge(monkeypatch):
    import base64
    import json
    from pathlib import Path

    report = native_series(monkeypatch)
    monkeypatch.delenv("GITHUB_RUN_ID")
    gate = json.loads(Path("docs/evidence/issue-4284/gate-run-40551187519.json").read_text())

    class API:
        def __init__(self):
            self.comments = []
            self.pr = None
            self.creations = 0

        def pages(self, path, **params):
            if path.endswith("/comments"):
                return self.comments
            if path.endswith("/pulls"):
                return [self.pr] if self.pr else []
            raise AssertionError(path)

        def optional(self, path):
            return None

        def request(self, method, path, payload=None):
            if "/actions/runs/" in path:
                index = int(path.rsplit("/", 1)[1]) - 1000
                return {
                    "path": follow.ROOT.replace("/repos/stranske/Workflows", "")
                    + ".github/workflows/health-85-ci-time-budget.yml",
                    "head_branch": "main",
                    "event": "schedule",
                    "run_attempt": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": (NOW - timedelta(days=6 - index)).isoformat(),
                }
            if "/contents/" in path:
                return {"content": base64.b64encode(json.dumps(gate).encode()).decode()}
            if path.endswith("/comments"):
                self.comments.append(payload)
                return {}
            if path.endswith("/issues/4284"):
                return {"state": "closed", "body": ""}
            if path.endswith("/pulls"):
                self.creations += 1
                self.pr = {
                    "html_url": "https://github.com/stranske/Workflows/pull/9999",
                    "merged_at": None,
                }
                assert payload["draft"] is False
                return self.pr
            return {"object": {"sha": "a" * 40}, "tree": {"sha": "b" * 40}, "sha": "c" * 40}

    api = API()
    first = follow.reconcile(api, report, NOW)
    assert first["action"] == "evidence_pr_created"
    assert not first["completion_reconciled"]
    assert follow.reconcile(api, report, NOW)["action"] == "existing_evidence_pr"
    api.pr["merged_at"] = NOW.isoformat()
    assert follow.reconcile(api, report, NOW)["completion_reconciled"]
    assert api.creations == 1
    assert len(api.comments) == 1
