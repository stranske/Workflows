import json
from pathlib import Path

from tools import post_ci_summary


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _sample_runs(states: dict[str, str | None] | None = None) -> list[dict[str, object]]:
    job_states = states or {
        "Core Tests (3.11)": "success",
        "Core Tests (3.12)": "success",
        "Docker Smoke": "success",
        "Gate": "success",
    }
    return [
        {
            "key": "ci",
            "displayName": "CI",
            "present": True,
            "status": "success",
            "id": 101,
            "run_attempt": 2,
            "html_url": "https://example/run/101",
            "jobs": [
                {"name": name, "conclusion": state, "html_url": "https://example/job"}
                for name, state in job_states.items()
            ],
        }
    ]


def test_load_required_groups_derives_from_runs() -> None:
    runs = _sample_runs()
    groups = post_ci_summary._load_required_groups(None, runs)

    labels = [group["label"] for group in groups]
    assert labels == ["Core Tests (3.11)", "Core Tests (3.12)", "Docker Smoke", "Gate"]
    assert groups[0]["patterns"] == [r"^Core\ Tests\ \(3\.11\)$"]
    assert groups[3]["patterns"] == [r"^Gate$"]


def test_collect_category_states_marks_docs_only_fast_pass() -> None:
    runs = _sample_runs(
        {
            "Core Tests (3.11)": "skipped",
            "Core Tests (3.12)": "skipped",
            "Docker Smoke": "skipped",
        }
    )
    category_states = post_ci_summary._collect_category_states(runs)

    assert post_ci_summary._is_docs_only_fast_pass(category_states) is True


def test_build_summary_comment_includes_required_sections(tmp_path: Path, monkeypatch) -> None:
    contexts_path = tmp_path / "contexts.json"
    _write_json(contexts_path, {"required_contexts": ["ci/required", "lint"]})
    monkeypatch.setenv("REQUIRED_CONTEXTS_FILE", str(contexts_path))

    runs = [
        {
            "key": "ci",
            "displayName": "CI",
            "present": True,
            "status": "failure",
            "id": 123,
            "run_attempt": 2,
            "html_url": "https://example/run/123",
            "jobs": [
                {"name": "Unit Tests", "conclusion": "failure", "html_url": "https://logs/unit"},
                {"name": "Lint", "conclusion": "success", "html_url": "https://logs/lint"},
            ],
        }
    ]

    coverage_stats = {
        "avg_latest": 71.5,
        "avg_delta": -1.2,
        "worst_latest": 60.0,
        "worst_delta": -5.5,
        "history_len": 12,
        "coverage_table_markdown": "| Job | Coverage |\n| --- | --- |\n| CI | 71.5% |",
    }
    coverage_delta = {
        "current": 71.5,
        "baseline": 73.0,
        "delta": -1.5,
        "drop": 2.0,
        "threshold": 1.0,
        "status": "below",
    }

    required_groups_env = json.dumps(
        [{"label": "required", "patterns": ["Unit Tests", "Lint"]}]
    )

    summary = post_ci_summary.build_summary_comment(
        runs=runs,
        head_sha="abc123",
        coverage_stats=coverage_stats,
        coverage_section="Extra coverage notes.",
        coverage_delta=coverage_delta,
        required_groups_env=required_groups_env,
    )

    assert "## Automated Status Summary" in summary
    assert "**Head SHA:** abc123" in summary
    assert "**Latest Runs:**" in summary
    assert "**Required contexts:** ci/required, lint" in summary
    assert "**Required:**" in summary
    assert "| **CI / Unit Tests** |" in summary
    assert "Coverage Overview" in summary
    assert "Coverage (jobs)" in summary
    assert "Coverage delta:" in summary
    assert "Extra coverage notes." in summary


def test_dedupe_runs_prefers_present_and_priority() -> None:
    runs = [
        {"key": "gate", "present": False, "status": "failure"},
        {"key": "gate", "present": True, "status": "success"},
        {"key": "gate", "present": True, "status": "failure"},
    ]

    deduped = post_ci_summary._dedupe_runs(runs)

    assert len(deduped) == 1
    assert deduped[0].get("status") == "failure"


def test_main_writes_github_output(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "output.txt"
    contexts_path = tmp_path / "contexts.json"
    _write_json(contexts_path, [])

    monkeypatch.setenv("RUNS_JSON", "[]")
    monkeypatch.setenv("REQUIRED_CONTEXTS_FILE", str(contexts_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    post_ci_summary.main()

    output_text = output_path.read_text(encoding="utf-8")
    assert "body<<EOF" in output_text
    assert "Automated Status Summary" in output_text
