import json
from datetime import UTC, datetime

import pytest
from scripts import langsmith_observability_health as health

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def _run(created_at: str, conclusion: str) -> dict[str, str]:
    return {"created_at": created_at, "conclusion": conclusion, "status": "completed"}


def test_workflow_health_detects_repeated_failures_and_stale_success() -> None:
    component = health.evaluate_workflow_runs(
        [
            _run("2026-08-15T10:00:00Z", "failure"),
            _run("2026-08-14T10:00:00Z", "failure"),
            _run("2026-08-01T10:00:00Z", "success"),
        ],
        name="dashboard_publication",
        now=NOW,
        max_age_hours=192,
        failure_threshold=2,
    )

    assert component["status"] == "degraded"
    assert component["consecutive_failures"] == 2
    assert any("last success" in reason for reason in component["reasons"])
    assert any("consecutive" in reason for reason in component["reasons"])


def test_fresh_trace_is_healthy() -> None:
    component = health.evaluate_trace_freshness(
        {"id": "run-1", "trace_id": "trace-1", "start_time": "2026-08-15T11:00:00Z"},
        now=NOW,
        max_age_hours=24,
    )

    assert component["status"] == "healthy"
    assert component["latest_trace_id"] == "trace-1"
    assert component["hours_since_trace"] == 1.0


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///tmp/langsmith.json",
        "http://api.smith.langchain.com",
        "https://user:secret@api.smith.langchain.com",
        "https://api.smith.langchain.com?redirect=file:///tmp/data",
    ],
)
def test_langsmith_endpoint_rejects_unsafe_urls(endpoint: str) -> None:
    with pytest.raises(ValueError, match="credential-free HTTPS"):
        health.validate_endpoint(endpoint)


def test_langsmith_endpoint_normalizes_trailing_slash() -> None:
    assert (
        health.validate_endpoint("https://api.smith.langchain.com/")
        == "https://api.smith.langchain.com"
    )


def test_overdue_pause_is_advisory() -> None:
    registry = {
        "repos": [
            {
                "repo": "stranske/Workflows",
                "rollout_status": "paused",
                "paused_at": "2026-06-13T13:36:33Z",
                "pause_reason": "artifact rollout paused",
                "pause_owner": "stranske/Workflows#2150",
                "resume_condition": "producer artifact is available",
                "review_by": "2026-08-01",
            }
        ]
    }

    component = health.evaluate_pauses(registry, now=NOW)

    assert component["status"] == "healthy"
    assert component["paused_entries"][0]["pause_owner"] == "stranske/Workflows#2150"
    assert component["reasons"] == []
    assert component["advisories"] == ["stranske/Workflows pause review was due 2026-08-01"]


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        (
            {"paused_at": "not-a-timestamp"},
            "paused_at is not a timezone-aware ISO timestamp",
        ),
        (
            {"paused_at": "2026-08-01T12:00:00"},
            "paused_at is not a timezone-aware ISO timestamp",
        ),
        ({"pause_owner": "   "}, "pause is missing: pause_owner"),
        ({"review_by": 20260815}, "pause is missing: review_by"),
        ({"review_by": "2026-07-31"}, "review_by cannot predate paused_at"),
    ],
)
def test_malformed_pause_metadata_requires_attention(
    override: dict[str, object], reason: str
) -> None:
    entry: dict[str, object] = {
        "repo": "stranske/Workflows",
        "rollout_status": "paused",
        "paused_at": "2026-08-01T12:00:00Z",
        "pause_reason": "artifact rollout paused",
        "pause_owner": "stranske/Workflows#2150",
        "resume_condition": "producer artifact is available",
        "review_by": "2026-08-15",
    }
    entry.update(override)

    component = health.evaluate_pauses({"repos": [entry]}, now=NOW)

    assert component["status"] == "degraded"
    assert any(reason in item for item in component["reasons"])


def test_workflow_run_loader_preserves_fetch_failure(tmp_path) -> None:
    payload = tmp_path / "runs.json"
    payload.write_text(
        json.dumps({"workflow_runs": [], "fetch_error": "GitHub API unavailable"}),
        encoding="utf-8",
    )

    runs, error = health.load_workflow_runs(payload)

    assert runs == []
    assert error == "GitHub API unavailable"


@pytest.mark.parametrize("has_key", [True, False])
def test_stale_workflows_remain_code_owned_unless_cloud_key_unavailable(
    tmp_path, monkeypatch, has_key
):
    from argparse import Namespace

    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps({"workflow_runs": [_run("2026-07-01T00:00:00Z", "failure")]}))
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"repos": []}))
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key" if has_key else "")
    monkeypatch.setattr(
        health, "query_latest_trace", lambda **kwargs: {"start_time": NOW.isoformat()}
    )
    report = health.build_report(
        Namespace(
            now=NOW.isoformat(),
            dashboard_runs=runs,
            conformance_runs=runs,
            registry=registry,
            endpoint=health.DEFAULT_ENDPOINT,
            project=health.DEFAULT_PROJECT,
            workflow_max_age_hours=192,
            failure_threshold=2,
            trace_max_age_hours=24,
        )
    )
    assert report["status"] == "degraded"
    assert report["human_attention_required"] is not has_key
