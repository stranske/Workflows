import importlib.util
from datetime import UTC, datetime

SPEC = importlib.util.spec_from_file_location(
    "dependency_sync_efficiency_metrics", "scripts/dependency_sync_efficiency_metrics.py"
)
metrics = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(metrics)


def test_fixture_classifies_all_generated_lanes_and_excludes_collab_admin():
    report = metrics.calculate(
        {
            "collection": {"history_complete": False, "limitations": ["fixture window"]},
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": 1,
                    "author": "renovate[bot]",
                    "head_ref": "renovate/x",
                    "state": "merged",
                    "source_commit": "a",
                },
                {
                    "repo": "stranske/App",
                    "number": 2,
                    "head_ref": "sync/workflows-a",
                    "state": "open",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "source_commit": "a",
                },
                {
                    "repo": "stranske/App",
                    "number": 3,
                    "head_ref": "deps/sync-dev-versions-a",
                    "state": "closed",
                    "body": "Supersedes #1",
                    "source_commit": "b",
                },
                {
                    "repo": "stranske/Collab-Admin",
                    "number": 4,
                    "head_ref": "sync/workflows-a",
                    "state": "open",
                },
            ],
            "workflow_runs": [{"head_sha": "a"}, {"head_sha": "a"}],
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    result = report["metrics"]
    assert result["lane_counts"] == {
        "dependency-bot": 1,
        "sync-generated": 1,
        "dev-tool-sync": 1,
        "traditional": 0,
    }
    assert result["generated_prs"] == 3
    assert result["stale"]["sync-generated"] == 1
    assert result["replacement"]["dev-tool-sync"] == 1
    assert result["collab_admin_excluded"] == 1
    assert result["source_change_to_consumer_pr_amplification"] == {"a": 2, "b": 1}
    assert result["actions_runs_per_source_change"]["a"] == 2
    assert result["avoidable_replacements_per_repo_batch"] == {"stranske/App/b": 1}
    assert report["advisory_slo"]["breaches"]["avoidable_replacements_per_repo_batch"] is True
    assert report["collection"]["history_complete"] is False


def test_labels_accepts_mapping_and_string_shapes():
    assert metrics.labels({"labels": [{"name": "Dependencies"}, "sync", None]}) == {
        "dependencies",
        "sync",
    }


def test_stale_and_replacement_rate_counts_one_pr_once():
    report = metrics.calculate(
        {
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": 1,
                    "head_ref": "sync/workflows-a",
                    "state": "open",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "body": "Supersedes #0",
                }
            ]
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    assert report["metrics"]["stale_or_replacement_numerator"] == 1
    assert report["metrics"]["stale_or_replacement_rate"] == 1.0


def test_stale_or_replacement_rate_breaches_at_five_percent_boundary():
    report = metrics.calculate(
        {
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": number,
                    "head_ref": f"sync/workflows-{number}",
                    "state": "closed" if number < 3 else "merged",
                    "body": "Supersedes #0" if number < 3 else "",
                }
                for number in range(1, 41)
            ]
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    assert report["metrics"]["stale_or_replacement_rate"] == 0.05
    assert report["advisory_slo"]["breaches"]["stale_or_replacement_rate"] is True


def test_fingerprint_ignores_generation_timestamp_but_tracks_material_evidence():
    snapshot = {
        "collection": {},
        "pulls": [
            {
                "repo": "stranske/App",
                "number": 1,
                "head_ref": "sync/workflows-a",
                "state": "open",
                "updated_at": "2026-01-10T00:00:00Z",
                "check_failure_cluster": ["Gate"],
            }
        ],
    }
    first = metrics.calculate(snapshot, datetime(2026, 1, 10, tzinfo=UTC))
    second = metrics.calculate(snapshot, datetime(2026, 1, 11, tzinfo=UTC))
    assert metrics.fingerprint(first) == metrics.fingerprint(second)
    snapshot["pulls"][0]["check_failure_cluster"] = ["Gate", "Python Tests"]
    changed = metrics.calculate(snapshot, datetime(2026, 1, 11, tzinfo=UTC))
    assert metrics.fingerprint(changed) != metrics.fingerprint(second)


def test_markdown_includes_denominators_limits_and_threshold_breach():
    report = metrics.calculate(
        {
            "collection": {"limitations": ["last 100 PRs per repo"]},
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": number,
                    "head_ref": f"sync/workflows-{number}",
                    "state": "open",
                    "updated_at": "2026-01-01T00:00:00Z",
                }
                for number in range(41)
            ],
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    text = metrics.markdown(report)
    assert report["advisory_slo"]["state"] == "breach"
    assert "Generated PRs: **41**" in text
    assert "Complete GitHub history: **false**" in text
    assert "last 100 PRs per repo" in text


def test_weekly_event_counts_use_reporting_window_timestamps():
    report = metrics.calculate(
        {
            "period": {
                "kind": "trailing-7-day-window",
                "start": "2026-01-03T00:00:00Z",
                "end": "2026-01-10T00:00:00Z",
            },
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": 1,
                    "head_ref": "sync/workflows-a",
                    "state": "open",
                    "created_at": "2026-01-05T00:00:00Z",
                    "updated_at": "2026-01-05T00:00:00Z",
                    "source_commit": "a",
                },
                {
                    "repo": "stranske/App",
                    "number": 2,
                    "head_ref": "sync/workflows-b",
                    "state": "merged",
                    "created_at": "2025-12-01T00:00:00Z",
                    "merged_at": "2026-01-06T00:00:00Z",
                    "source_commit": "b",
                },
                {
                    "repo": "stranske/App",
                    "number": 3,
                    "head_ref": "sync/workflows-old",
                    "state": "closed",
                    "created_at": "2025-11-01T00:00:00Z",
                    "closed_at": "2025-11-02T00:00:00Z",
                    "updated_at": "2026-01-09T00:00:00Z",
                    "source_commit": "c",
                },
            ],
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    assert report["metrics"]["created"]["sync-generated"] == 1
    assert report["metrics"]["merged"]["sync-generated"] == 1
    assert report["metrics"]["closed"]["sync-generated"] == 0
    assert report["metrics"]["generated_prs"] == 1


def test_markdown_lists_avoidable_replacement_breach_keys():
    report = metrics.calculate(
        {
            "pulls": [
                {
                    "repo": "stranske/App",
                    "number": 1,
                    "head_ref": "sync/workflows-a",
                    "state": "closed",
                    "body": "Supersedes #0",
                    "source_commit": "batch-1",
                }
            ]
            + [
                {
                    "repo": "stranske/App",
                    "number": number,
                    "head_ref": f"sync/workflows-{number}",
                    "state": "merged",
                    "source_commit": f"ok-{number}",
                }
                for number in range(2, 41)
            ],
        },
        datetime(2026, 1, 10, tzinfo=UTC),
    )
    text = metrics.markdown(report)
    assert report["advisory_slo"]["breaches"]["avoidable_replacements_per_repo_batch"] is True
    assert "Avoidable replacement repository/batches: **1**" in text
    assert "Avoidable replacement: stranske/App/batch-1 (1)" in text
    assert "Stale/replacement rate:" in text
