from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add script directory to path before importing gate_summary
SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".github" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import gate_summary  # noqa: E402


def write_summary(
    root: Path,
    runtime: str,
    *,
    format_outcome: str = "success",
    lint: str = "success",
    tests: str = "success",
    type_check: str = "success",
) -> None:
    summary_dir = root / "downloads" / runtime
    summary_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "python_version": runtime,
        "checks": {
            "format": {"outcome": format_outcome},
            "lint": {"outcome": lint},
            "tests": {"outcome": tests},
            "type_check": {"outcome": type_check},
            "coverage_minimum": {"outcome": "success"},
        },
        "coverage": {"percent": 91.23},
    }
    (summary_dir / "summary.json").write_text(json.dumps(payload), encoding="utf-8")


def test_doc_only_summary_state() -> None:
    context = gate_summary.SummaryContext(
        doc_only=True,
        run_core=False,
        reason="docs_only",
        python_result="success",
        docker_result="skipped",
        docker_changed=False,
        artifacts_root=Path("/tmp/nonexistent"),
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "success"
    assert "docs-only" in "\n".join(result.lines)
    assert any("| docs-only | success |" in line for line in result.lines)
    assert result.format_failure is False


def test_active_summary_reads_artifacts(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.11")

    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="success",
        docker_result="success",
        docker_changed=False,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    joined = "\n".join(result.lines)
    assert result.state == "success"
    assert "Gate status" in joined
    assert "Reported coverage" in joined
    assert "Docker smoke skipped" in joined
    assert "| docker-smoke | success |" in joined
    assert result.cosmetic_failure is False
    assert result.format_failure is False


@pytest.mark.parametrize(
    "python_outcome, expected_state",
    [("failure", "failure"), ("success", "success")],
)
def test_summary_state_reflects_python_outcome(
    tmp_path: Path, python_outcome: str, expected_state: str
) -> None:
    write_summary(tmp_path, "3.12", lint="failure", tests=python_outcome)
    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result=python_outcome,
        docker_result="success",
        docker_changed=True,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == expected_state
    assert result.cosmetic_failure is False
    assert result.format_failure is False


def test_cosmetic_failure_detected(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.11", format_outcome="failure")
    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="failure",
        docker_result="success",
        docker_changed=False,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "failure"
    assert result.cosmetic_failure is True
    assert result.failure_checks == ("format",)
    assert result.format_failure is True


def test_cosmetic_failure_rejects_other_failures(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.11", tests="failure")
    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="failure",
        docker_result="success",
        docker_changed=False,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "failure"
    assert result.cosmetic_failure is False
    assert result.format_failure is False


def test_cosmetic_failure_reports_all_allowed_checks(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.11", format_outcome="failure")
    write_summary(tmp_path, "3.12", lint="failure")

    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="failure",
        docker_result="success",
        docker_changed=False,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "failure"
    assert result.cosmetic_failure is True
    assert result.failure_checks == ("format", "lint")
    assert result.format_failure is True


def test_normalize_handles_missing_and_blank_values() -> None:
    assert gate_summary._normalize(None) == "unknown"
    assert gate_summary._normalize("   ") == "unknown"
    assert gate_summary._normalize(" SUCCESS ") == "success"


def test_load_summary_records_handles_missing_and_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts_root = tmp_path / "artifacts"

    # Missing downloads directory returns an empty list
    assert gate_summary._load_summary_records(artifacts_root) == []

    downloads = artifacts_root / "downloads" / "job"
    downloads.mkdir(parents=True)
    (downloads / "summary.json").write_text("{not-json", encoding="utf-8")

    # Invalid JSON entries are ignored
    assert gate_summary._load_summary_records(artifacts_root) == []

    # Inject a record outside of artifacts_root to exercise the ValueError branch
    outside = tmp_path / "outside" / "summary.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{}", encoding="utf-8")

    original_rglob = Path.rglob

    def fake_rglob(self: Path, pattern: str):
        if self == artifacts_root / "downloads":
            return [outside]
        return original_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    assert gate_summary._load_summary_records(artifacts_root) == [{"job_name": "unknown"}]

    # Non-dict payloads are skipped safely
    broken = downloads / "bad_type" / "summary.json"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("[]", encoding="utf-8")
    assert gate_summary._load_summary_records(artifacts_root) == [{"job_name": "unknown"}]


def test_detect_cosmetic_failure_handles_non_mappings() -> None:
    # Non-mapping records are ignored
    assert gate_summary._detect_cosmetic_failure(["oops"]) == (False, ())
    # Records missing mapping checks short-circuit to False
    assert gate_summary._detect_cosmetic_failure([{"checks": []}]) == (False, ())
    assert gate_summary._normalize_check_outcome(None) == "unknown"


def test_collect_table_handles_missing_percent() -> None:
    record = {
        "python_version": "3.12",
        "job_name": "gate",
        "checks": {
            "lint": {"outcome": "success"},
            "type_check": {"outcome": "success"},
            "tests": {"outcome": "success"},
            "coverage_minimum": {"outcome": "pending"},
        },
        "coverage": {"percent": None},
    }

    (
        table,
        lint_entries,
        type_entries,
        test_entries,
        coverage_entries,
        coverage_percents,
        job_results,
    ) = gate_summary._collect_table([record])

    assert table[-1].endswith("| — |")
    assert coverage_percents == []

    lines = gate_summary._active_lines(
        table,
        lint_entries,
        type_entries,
        test_entries,
        coverage_entries,
        coverage_percents,
        job_results,
        docker_result="pending",
    )

    assert not any("Reported coverage" in line for line in lines)


def test_doc_only_lines_reports_custom_reason() -> None:
    lines = gate_summary._doc_only_lines("workflow_only")
    assert "workflow_only" in "\n".join(lines)


def test_doc_only_lines_defaults_reason() -> None:
    lines = gate_summary._doc_only_lines("")
    assert "docs-only" in "\n".join(lines)


def test_summarize_handles_skipped_python_when_core_runs(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.11")
    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="skipped",
        docker_result="success",
        docker_changed=False,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "failure"
    assert "Python CI result: skipped." in result.description


def test_summarize_handles_docker_failures(tmp_path: Path) -> None:
    write_summary(tmp_path, "3.12")
    context = gate_summary.SummaryContext(
        doc_only=False,
        run_core=True,
        reason="",
        python_result="success",
        docker_result="failure",
        docker_changed=True,
        artifacts_root=tmp_path,
        summary_path=None,
        output_path=None,
    )

    result = gate_summary.summarize(context)
    assert result.state == "failure"
    assert "Docker smoke result: failure." in result.description
    assert any("docker-smoke" in line for line in result.lines)


def test_build_context_reads_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DOC_ONLY", "TRUE")
    monkeypatch.setenv("RUN_CORE", "False")
    monkeypatch.setenv("REASON", "workflow_only")
    monkeypatch.setenv("PYTHON_RESULT", "FAILURE")
    monkeypatch.setenv("DOCKER_RESULT", "cancelled")
    monkeypatch.setenv("DOCKER_CHANGED", "TRUE")
    artifacts_root = tmp_path / "gate_artifacts"
    monkeypatch.setenv("GATE_ARTIFACTS_ROOT", str(artifacts_root))
    summary_path = tmp_path / "summary" / "summary.md"
    output_path = tmp_path / "output" / "output.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    context = gate_summary.build_context()
    assert context.doc_only is True
    assert context.run_core is False
    assert context.reason == "workflow_only"
    assert context.python_result == "FAILURE"
    assert context.docker_result == "cancelled"
    assert context.docker_changed is True
    assert context.artifacts_root == artifacts_root
    assert context.summary_path == summary_path
    assert context.output_path == output_path


def test_resolve_path_handles_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOT_SET", raising=False)
    assert gate_summary._resolve_path("NOT_SET") is None


def test_main_writes_summary_and_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary_path = tmp_path / "summary" / "summary.md"
    output_path = tmp_path / "output" / "output.txt"

    monkeypatch.setenv("DOC_ONLY", "true")
    monkeypatch.setenv("RUN_CORE", "false")
    monkeypatch.delenv("REASON", raising=False)
    monkeypatch.delenv("PYTHON_RESULT", raising=False)
    monkeypatch.delenv("DOCKER_RESULT", raising=False)
    monkeypatch.delenv("DOCKER_CHANGED", raising=False)
    monkeypatch.setenv("GATE_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))

    assert gate_summary.main() == 0

    summary_text = summary_path.read_text(encoding="utf-8")
    output_text = output_path.read_text(encoding="utf-8")
    assert "Docs-only" in summary_text
    assert "state=success" in output_text


def test_write_summary_and_outputs(tmp_path: Path) -> None:
    result = gate_summary.SummaryResult(
        lines=["one", "two"],
        state="failure",
        description="bad",
        cosmetic_failure=True,
        failure_checks=("format", "lint"),
        format_failure=True,
    )

    summary_path = tmp_path / "summary" / "summary.md"
    output_path = tmp_path / "outputs" / "values.txt"

    gate_summary._write_summary(result, None)
    gate_summary._write_outputs(result, None)

    gate_summary._write_summary(result, summary_path)
    gate_summary._write_outputs(result, output_path)

    summary_text = summary_path.read_text(encoding="utf-8")
    output_text = output_path.read_text(encoding="utf-8")

    assert "one\ntwo" in summary_text
    assert "state=failure" in output_text
    assert "failure_checks=format,lint" in output_text
    assert "format_failure=true" in output_text

    clean_result = gate_summary.SummaryResult(
        lines=["clean"],
        state="success",
        description="ok",
        cosmetic_failure=False,
        failure_checks=(),
        format_failure=False,
    )

    gate_summary._write_outputs(clean_result, output_path)
    updated_text = output_path.read_text(encoding="utf-8")
    assert "failure_checks=" in updated_text
