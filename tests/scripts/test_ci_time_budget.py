import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from scripts import ci_time_budget as budget

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)
REPO = "stranske/Example"


class FakeGitHub:
    def __init__(self):
        self.issues = []
        self.calls = []

    def pages(self, path, key=None, **params):
        assert path.endswith("/issues")
        assert params == {"state": "open", "labels": "ci-budget"}
        return [issue for issue in self.issues if issue.get("state", "open") == "open"]

    def optional(self, path):
        return {"name": path.rsplit("/", 1)[-1]}

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "POST" and path.endswith("/issues"):
            issue = {"number": 42, "created_at": NOW.isoformat(), **payload}
            self.issues.append(issue)
            return issue
        if method == "PATCH":
            self.issues[0].update(payload)
        return {}


def metrics(p50=15):
    return {
        "p50": p50,
        "p90": p50 + 2,
        "longest_job": {
            "name": "python ci / test (3.13)",
            "minutes": 20,
            "url": "https://example.org/job",
        },
    }


@pytest.mark.parametrize(
    "distance,expected",
    [(0, 0), (0.25, 0.05), (0.5, 0.1), (0.75, 0.2), (1.0, 0.4), (2.0, 0.5), (1000, 0.5)],
)
def test_share_curve(distance, expected):
    assert budget.share(distance) == pytest.approx(expected)


def test_issue_filed_once_per_repo_and_updated_without_destroying_tasks():
    api = FakeGitHub()
    row = budget.observation({}, metrics(), NOW)
    budget.reconcile(api, REPO, row)
    first_body = api.issues[0]["body"]
    for day in range(1, 4):
        row = budget.observation(row, metrics(), NOW + timedelta(days=day))
        budget.reconcile(api, REPO, row)
    creations = [c for c in api.calls if c[0] == "POST" and c[1].endswith("/issues")]
    assert len(creations) == 1
    assert creations[0][2]["labels"] == ["ci-budget", "priority:high"]
    for heading in (
        "Why",
        "Scope",
        "Non-Goals",
        "Tasks",
        "Acceptance Criteria",
        "Implementation Notes",
    ):
        assert f"## {heading}" in first_body
    assert "python ci / test (3.13)" in first_body
    assert "15.00" in first_body
    assert "10 min" in first_body
    assert "10.00%" in first_body
    assert api.issues[0]["body"] == first_body
    assert row["filing_latency_hours"] == 0
    assert row["filed_under_24h"] is True


def test_issue_closed_after_seven_under_target_days(capsys):
    api = FakeGitHub()
    row = budget.observation({}, metrics(20), NOW)
    budget.reconcile(api, REPO, row)
    for day in range(1, 8):
        row = budget.observation(row, metrics(8), NOW + timedelta(days=day))
        budget.reconcile(api, REPO, row)
        assert row["share"] == 0
        assert row["drainable_in"] == 7 - day
        assert (api.issues[0].get("state") == "closed") is (day == 7)
    closings = [c for c in api.calls if c[0] == "PATCH"]
    assert len(closings) == 1
    comment = [c[2]["body"] for c in api.calls if c[1].endswith("/comments")][-1]
    for day in range(1, 8):
        assert f"2026-10-{17 + day}: 8.00 min" in comment
    assert "share=0, drainable_in=0" in comment
    assert "share=0, issue closed" in capsys.readouterr().out
    assert row["issue_numbers"] == []


def test_recurrence_starts_new_filing_clock():
    previous = {"first_over_target_at": NOW.isoformat(), "drained_at": NOW.isoformat()}
    row = budget.observation(previous, metrics(), NOW + timedelta(days=20))
    assert row["first_over_target_at"] == (NOW + timedelta(days=20)).isoformat()
    assert "drained_at" not in row


@pytest.mark.parametrize("interruption", [None, 11, "missing"])
def test_gap_unknown_or_over_target_resets_recovery(interruption):
    row = {}
    for day in range(7):
        if day == 3 and interruption == "missing":
            continue
        measurement = None if day == 3 and interruption is None else metrics(8)
        if day == 3 and interruption == 11:
            measurement = metrics(11)
        row = budget.observation(row, measurement, NOW + timedelta(days=day))
    assert row["drainable_in"] == 4


def test_same_day_reruns_do_not_accelerate_drain_and_target_equality_is_healthy():
    row = {}
    for _ in range(10):
        row = budget.observation(row, metrics(10), NOW)
    assert row["share"] == 0
    assert row["drainable_in"] == 6
    assert len(row["p50_series"]) == 1


def test_unknown_cannot_close_issue_or_reserve_slots():
    api = FakeGitHub()
    row = budget.observation({}, metrics(), NOW)
    budget.reconcile(api, REPO, row)
    for day in range(1, 8):
        row = budget.observation(row, None, NOW + timedelta(days=day))
        budget.reconcile(api, REPO, row)
    assert row["share"] is None
    assert row["p50"] is None
    assert row["drainable_in"] == 7
    assert not any(c[0] == "PATCH" for c in api.calls)


class ActionsAPI:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append(path)
        query = parse_qs(urlsplit(path).query)
        assert query["status"] == ["completed"]
        assert "2026-10-10" in query["created"][0]
        return {
            "total_count": len(self.jobs),
            "workflow_runs": [{"id": i, "conclusion": "success"} for i in self.jobs],
        }

    def pages(self, path, key=None, **params):
        assert key == "jobs"
        assert params == {"filter": "latest"}
        return self.jobs[int(path.split("/")[-2])]


def job(name, minutes, **overrides):
    return {
        "name": name,
        "conclusion": "success",
        "started_at": (NOW - timedelta(minutes=minutes + 1)).isoformat(),
        "completed_at": (NOW - timedelta(minutes=1)).isoformat(),
        "html_url": "https://example.org/job",
        **overrides,
    }


def test_measure_uses_per_run_bottlenecks_and_interpolated_percentiles():
    api = ActionsAPI(
        {
            1: [job("setup", 1), job("test (3.13)", 10), job("skipped", 99, conclusion="skipped")],
            2: [job("setup", 1), job("test (3.14)", 20)],
            3: [job("setup", 1), job("test (3.13)", 30)],
        }
    )
    measured = budget.measure(REPO, api=api, now=NOW)
    assert measured["p50"] == 20
    assert measured["p90"] == 28
    assert measured["sample_count"] == 3
    assert measured["longest_job"] == {
        "name": "test (3.13)",
        "minutes": 30,
        "url": "https://example.org/job",
    }


@pytest.mark.parametrize("jobs", [{}, {1: [job("skipped", 1, conclusion="skipped")]}])
def test_empty_or_skipped_measurement_is_unknown(jobs):
    with pytest.raises(RuntimeError, match="No completed executed Gate jobs"):
        budget.measure(REPO, api=ActionsAPI(jobs), now=NOW)


def test_measure_fetches_all_job_pages():
    class API(budget.GitHub):
        def __init__(self):
            pass

        def request(self, method, path, payload=None):
            if path.endswith("per_page=1"):
                return {"total_count": 1}
            if "/runs?" in path:
                return {"total_count": 1, "workflow_runs": [{"id": 1, "conclusion": "success"}]}
            page = parse_qs(urlsplit(path).query)["page"][0]
            jobs = [job("setup", 1)] * 100 if page == "1" else [job("slow", 25)]
            return {"total_count": 101, "jobs": jobs}

    assert budget.measure(REPO, api=API(), now=NOW)["p50"] == 25


def test_filtered_run_ceiling_is_subdivided_and_boundaries_deduplicated():
    class API:
        def request(self, method, path, payload=None):
            query = parse_qs(urlsplit(path).query)
            window = query["created"][0]
            start, end = map(datetime.fromisoformat, window.split(".."))
            if (end - start).days == 7:
                return {"total_count": 1001}
            ids = range(1, 502) if start == NOW - timedelta(days=7) else range(501, 1002)
            ids = list(ids)
            if query["per_page"] == ["1"]:
                return {"total_count": len(ids)}
            page = int(query["page"][0])
            return {
                "total_count": len(ids),
                "workflow_runs": [{"id": i} for i in ids[(page - 1) * 100 : page * 100]],
            }

    assert len(budget.gate_runs(API(), REPO, NOW - timedelta(days=7), NOW)) == 1001


def test_publish_json_includes_drain_and_uses_expected_sha(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "REPORT_PATH", tmp_path / "ci-budget.json")
    report = {REPO: budget.observation({}, metrics(), NOW)}
    api = FakeGitHub()

    def request(method, path, payload=None):
        assert method == "PUT"
        assert payload["sha"] == "previous-blob"
        assert payload["branch"] == "ci-time-budget"
        content = json.loads(base64.b64decode(payload["content"]))
        assert content[REPO]["drainable_in"] == 7
        assert content[REPO]["distance"] == 0.5
        assert content[REPO]["share"] == 0.1
        return {"content": {"sha": "new-blob"}}

    api.request = request
    assert budget.publish(report, api=api, sha="previous-blob") == "new-blob"
    assert json.loads((tmp_path / "ci-budget.json").read_text()) == report


def test_run_persists_first_detection_before_failed_issue_write(monkeypatch):
    snapshots = []
    monkeypatch.setattr(budget, "load_report", lambda api: ({}, None))
    monkeypatch.setattr(budget, "measure", lambda *a, **kw: metrics())

    def publish(report, **kwargs):
        snapshots.append(json.loads(json.dumps(report)))
        return "sha"

    def reconcile(*args):
        raise RuntimeError("permission denied")

    monkeypatch.setattr(budget, "publish", publish)
    monkeypatch.setattr(budget, "reconcile", reconcile)
    assert budget.run(FakeGitHub(), [REPO], NOW) == 1
    assert snapshots[0][REPO]["first_over_target_at"] == NOW.isoformat()
    assert snapshots[1][REPO]["error"] == "permission denied"


def test_filing_latency_preserves_first_detection_across_days():
    api = FakeGitHub()
    row = budget.observation({}, metrics(), NOW - timedelta(days=2))
    row = budget.observation(row, metrics(), NOW)
    budget.reconcile(api, REPO, row)
    assert row["filing_latency_hours"] == 48
    assert row["filed_under_24h"] is False


def test_first_publish_creates_branch_only_after_report_commit_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "REPORT_PATH", tmp_path / "ci-budget.json")
    calls = []

    def request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path.endswith("Workflows"):
            return {"default_branch": "main"}
        if method == "GET" and path.endswith("/heads/main"):
            return {"object": {"sha": "parent"}}
        if method == "GET" and path.endswith("/commits/parent"):
            return {"tree": {"sha": "base-tree"}}
        if path.endswith("/blobs"):
            assert json.loads(payload["content"])[REPO]["drainable_in"] == 7
            return {"sha": "report-blob"}
        if path.endswith("/trees"):
            assert payload["tree"][0]["sha"] == "report-blob"
            assert payload["base_tree"] == "base-tree"
            return {"sha": "report-tree"}
        if path.endswith("/commits"):
            assert payload["tree"] == "report-tree"
            return {"sha": "report-commit"}
        assert path.endswith("/refs")
        assert payload == {"ref": "refs/heads/ci-time-budget", "sha": "report-commit"}
        return {}

    api = FakeGitHub()
    api.request = request
    report = {REPO: budget.observation({}, metrics(), NOW)}
    assert budget.publish(report, api=api, sha=None) == "report-blob"
    assert calls[-1][1].endswith("/git/refs")


def test_no_mutation_when_state_publication_fails(monkeypatch):
    monkeypatch.setattr(budget, "load_report", lambda api: ({}, None))
    monkeypatch.setattr(budget, "measure", lambda *a, **kw: metrics())

    def fail(*args, **kwargs):
        raise RuntimeError("state write failed")

    def forbidden(*args, **kwargs):
        pytest.fail("Cannot reconcile before durable state publication")

    monkeypatch.setattr(budget, "publish", fail)
    monkeypatch.setattr(budget, "reconcile", forbidden)
    with pytest.raises(RuntimeError, match="state write failed"):
        budget.run(FakeGitHub(), [REPO], NOW)


def test_partial_measurement_failure_continues_other_repos(monkeypatch):
    reconciled = []
    snapshots = []
    monkeypatch.setattr(budget, "load_report", lambda api: ({}, None))

    def measure(repo, **kwargs):
        if repo == REPO:
            raise RuntimeError("Actions unavailable")
        return metrics(8)

    def publish(report, **kwargs):
        snapshots.append(json.loads(json.dumps(report)))
        return "sha"

    def reconcile(api, repo, row):
        reconciled.append((repo, row["status"]))

    monkeypatch.setattr(budget, "measure", measure)
    monkeypatch.setattr(budget, "publish", publish)
    monkeypatch.setattr(budget, "reconcile", reconcile)
    assert budget.run(FakeGitHub(), [REPO, budget.SOURCE_REPO], NOW) == 1
    assert reconciled == [(REPO, "unknown"), (budget.SOURCE_REPO, "measured")]
    assert snapshots[-1][REPO]["share"] is None
    assert snapshots[-1][budget.SOURCE_REPO]["share"] == 0


def test_missing_report_on_existing_state_branch_is_not_an_empty_history():
    api = FakeGitHub()

    def fail(*args, **kwargs):
        raise RuntimeError("GitHub API error 404: report missing")

    api.request = fail
    with pytest.raises(RuntimeError, match="report missing"):
        budget.load_report(api)


def test_share_finite_and_under_target_guards():
    assert budget.share(-0.1) == 0
    with pytest.raises(ValueError, match="finite"):
        budget.share(float("nan"))


def test_under_target_does_not_create_work():
    api = FakeGitHub()
    row = budget.observation({}, metrics(8), NOW)
    budget.reconcile(api, REPO, row)
    assert api.calls == []


def test_denied_closure_does_not_claim_issue_closed(capsys):
    api = FakeGitHub()
    row = budget.observation({}, metrics(), NOW)
    budget.reconcile(api, REPO, row)
    for day in range(1, 8):
        row = budget.observation(row, metrics(8), NOW + timedelta(days=day))

    original_request = api.request

    def request(method, path, payload=None):
        if method == "PATCH":
            raise RuntimeError("close denied")
        return original_request(method, path, payload)

    api.request = request
    with pytest.raises(RuntimeError, match="close denied"):
        budget.reconcile(api, REPO, row)
    assert "drained_at" not in row
    assert "issue closed" not in capsys.readouterr().out
    assert "issue closed" not in api.calls[-1][2]["body"]
