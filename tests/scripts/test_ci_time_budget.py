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


def test_source_repo_retains_native_daily_observations_within_thirty_days(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", budget.SOURCE_REPO)
    monkeypatch.setenv("GITHUB_RUN_ID", "42809062881")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    stale_day = (NOW.date() - timedelta(days=30)).isoformat()
    previous = {
        "daily_observations": {
            stale_day: {
                "date": stale_day,
                "p50_minutes": 9.0,
                "run_id": 100,
            }
        }
    }
    row = budget.observation(previous, metrics(9.5), NOW)
    today = NOW.date().isoformat()
    assert stale_day not in row["daily_observations"]
    assert row["daily_observations"][today] == {
        "date": today,
        "p50_minutes": 9.5,
        "run_id": 42809062881,
        "run_attempt": 2,
        "measured_at": NOW.isoformat(),
        "window_start": (NOW - timedelta(days=7)).isoformat(),
        "source_run_url": f"https://github.com/{budget.SOURCE_REPO}/actions/runs/42809062881",
    }


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

    def request_no_sha(method, path, payload=None):
        assert method == "PUT"
        assert "sha" not in payload
        return {"content": {"sha": "empty-sha-blob"}}

    api.request = request_no_sha
    assert budget.publish(report, api=api, sha="") == "empty-sha-blob"


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


def test_completed_run_jobs_are_reused_only_for_the_exact_revision(tmp_path):
    class Cached(budget.GitHub):
        def pages(self, path, key=None, **params):
            self.reads += 1
            if self.failure:
                raise RuntimeError("unavailable")
            return [{"run_id": 123, "status": self.status}]

    api = Cached("fixture-token")
    api.cache_dir = tmp_path
    api.reads, api.failure, api.status = 0, False, "completed"
    run = {
        "id": 123,
        "run_attempt": 1,
        "status": "completed",
        "head_sha": "a" * 40,
        "updated_at": NOW.isoformat(),
    }
    first = api.run_jobs(REPO, run)
    assert api.run_jobs(REPO, run) == first and api.reads == 1
    run["run_attempt"] = 2
    api.run_jobs(REPO, run)
    assert api.reads == 2
    run["updated_at"] = (NOW + timedelta(seconds=1)).isoformat()
    api.run_jobs(REPO, run)
    assert api.reads == 3
    for path in tmp_path.glob("*.json"):
        path.write_text("{incomplete")
    api.run_jobs(REPO, run)
    assert api.reads == 4
    run["run_attempt"] = 3
    api.status = "in_progress"
    api.run_jobs(REPO, run)
    api.run_jobs(REPO, run)
    assert api.reads == 6
    api.failure = True
    with pytest.raises(RuntimeError, match="unavailable"):
        api.run_jobs(REPO, run)
    assert api.reads == 7


def test_github_client_and_pagination_edge_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(budget, "is_owner_excluded", lambda repo: repo == "excluded/repo")
    api = budget.GitHub("tok")
    api.cache_dir = tmp_path

    with pytest.raises(ValueError, match="Repository is excluded"):
        api.run_jobs("excluded/repo", {"id": 1})

    # Cache file exists with valid JSON and "jobs" key, but schema mismatch triggers refetch
    run = {
        "id": 999,
        "run_attempt": 1,
        "status": "completed",
        "head_sha": "b" * 40,
        "updated_at": NOW.isoformat(),
    }
    monkeypatch.setattr(
        api,
        "pages",
        lambda *a, **kw: [{"run_id": 999, "status": "completed"}],
    )
    api.run_jobs(REPO, run)
    for cache_file in tmp_path.glob("*.json"):
        data = json.loads(cache_file.read_text())
        data["schema"] = "wrong-schema"
        cache_file.write_text(json.dumps(data))
    assert api.run_jobs(REPO, run) == [{"run_id": 999, "status": "completed"}]

    # request delegates to api_client._request_json
    called = []
    monkeypatch.setattr(
        budget.api_client,
        "_request_json",
        lambda method, url, token, payload, max_attempts: (
            called.append((method, url, token, payload, max_attempts)) or {"ok": True}
        ),
    )
    assert api.request("GET", "/test") == {"ok": True}
    assert called[-1][4] == 3

    # optional handles 404 and re-raises other RuntimeErrors
    monkeypatch.setattr(
        api,
        "request",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("GitHub API error 404: not found")),
    )
    assert api.optional("/missing") is None

    monkeypatch.setattr(
        api,
        "request",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("GitHub API error 500: boom")),
    )
    with pytest.raises(RuntimeError, match="500: boom"):
        api.optional("/boom")

    # pages without key and incomplete pagination error
    p_api = budget.GitHub("tok")
    monkeypatch.setattr(p_api, "request", lambda *a, **kw: [{"id": 1}])
    assert p_api.pages("/items") == [{"id": 1}]

    monkeypatch.setattr(
        p_api,
        "request",
        lambda *a, **kw: {"total_count": 5, "items": [{"id": 1}]},
    )
    with pytest.raises(RuntimeError, match="Incomplete or changing pagination"):
        p_api.pages("/items", "items")

    monkeypatch.setattr(
        p_api,
        "request",
        lambda *a, **kw: [{"id": i} for i in range(100)],
    )
    with pytest.raises(RuntimeError, match="Pagination limit reached"):
        p_api.pages("/infinite")


def test_gate_runs_and_measure_validation_errors(monkeypatch):
    class CeilingAPI:
        def request(self, method, path, payload=None):
            return {"total_count": 1001}

    with pytest.raises(RuntimeError, match="exceeds the API ceiling within one second"):
        budget.gate_runs(CeilingAPI(), REPO, NOW, NOW + timedelta(seconds=1))

    class ChangingSubdivisionAPI:
        def request(self, method, path, payload=None):
            query = parse_qs(urlsplit(path).query)
            start, end = map(datetime.fromisoformat, query["created"][0].split(".."))
            if (end - start).total_seconds() > 10:
                return {"total_count": 1001}
            return {"total_count": 1, "workflow_runs": [{"id": 1}]}

    with pytest.raises(RuntimeError, match="Gate run window changed during subdivision"):
        budget.gate_runs(ChangingSubdivisionAPI(), REPO, NOW, NOW + timedelta(seconds=20))

    class ChangingPagingAPI:
        def __init__(self):
            self.calls = 0

        def request(self, method, path, payload=None):
            self.calls += 1
            if self.calls == 1:
                return {"total_count": 1}
            return {"total_count": 2, "workflow_runs": [{"id": 1}]}

    with pytest.raises(RuntimeError, match="Gate run count changed while paging"):
        budget.gate_runs(ChangingPagingAPI(), REPO, NOW - timedelta(days=1), NOW)

    class DuplicateRunsAPI:
        def request(self, method, path, payload=None):
            if "per_page=1&" in path or path.endswith("per_page=1"):
                return {"total_count": 2}
            return {"total_count": 2, "workflow_runs": [{"id": 1}, {"id": 1}]}

    with pytest.raises(RuntimeError, match="Incomplete Gate run window"):
        budget.gate_runs(DuplicateRunsAPI(), REPO, NOW - timedelta(days=1), NOW)

    monkeypatch.setattr(budget, "is_owner_excluded", lambda repo: repo == "excluded/repo")
    with pytest.raises(ValueError, match="Repository is excluded"):
        budget.measure("excluded/repo", api=FakeGitHub(), now=NOW)
    monkeypatch.setattr(budget, "is_owner_excluded", lambda repo: False)

    # Measure skips cancelled runs, jobs outside window, and rejects jobs missing timestamps
    monkeypatch.setattr(
        budget,
        "gate_runs",
        lambda *a: [
            {"id": 1, "conclusion": "cancelled"},
            {"id": 2, "conclusion": "success"},
        ],
    )

    class JobChecksAPI:
        def __init__(self, jobs_list):
            self.jobs_list = jobs_list

        def run_jobs(self, repo, run):
            return self.jobs_list

    with pytest.raises(RuntimeError, match="Executed Gate job has no duration"):
        budget.measure(
            REPO,
            api=JobChecksAPI([{"name": "j", "conclusion": "success", "started_at": None}]),
            now=NOW,
        )

    outside_job = job(
        "old",
        5,
        started_at=(NOW - timedelta(days=9)).isoformat(),
        completed_at=(NOW - timedelta(days=8)).isoformat(),
    )
    valid_job = job("curr", 8)
    res = budget.measure(REPO, api=JobChecksAPI([outside_job, valid_job]), now=NOW)
    assert res["p50"] == 8


def test_reconcile_creates_missing_labels_and_load_report_and_main(monkeypatch):
    api = FakeGitHub()
    api.optional = lambda path: None
    row = budget.observation({}, metrics(), NOW)
    budget.reconcile(api, REPO, row)
    label_posts = [c for c in api.calls if c[0] == "POST" and c[1].endswith("/labels")]
    assert len(label_posts) == 2

    # load_report when branch ref is None vs existing
    assert budget.load_report(api) == ({}, None)
    api.optional = lambda path: {"ref": "refs/heads/ci-time-budget"}
    encoded = base64.b64encode(b'{"hello": "world"}').decode()
    api.request = lambda method, path, payload=None: {"content": encoded, "sha": "abc123"}
    assert budget.load_report(api) == ({"hello": "world"}, "abc123")

    # run skips excluded repo
    monkeypatch.setattr(budget, "is_owner_excluded", lambda repo: repo == "excluded/repo")
    monkeypatch.setattr(budget, "load_report", lambda a: ({}, "sha1"))
    monkeypatch.setattr(budget, "measure", lambda *a, **kw: metrics(8))
    monkeypatch.setattr(budget, "publish", lambda *a, **kw: "sha2")
    assert budget.run(FakeGitHub(), ["excluded/repo"], NOW) == 0
    monkeypatch.setattr(budget, "is_owner_excluded", lambda repo: False)

    # main without GH_TOKEN and with GH_TOKEN
    monkeypatch.setattr("sys.argv", ["ci_time_budget.py"])
    monkeypatch.delenv("GH_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="GH_TOKEN"):
        budget.main()

    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(budget, "extract_repos", lambda p: [REPO])
    monkeypatch.setattr(budget, "run", lambda a, r, n: 0)
    assert budget.main() == 0
