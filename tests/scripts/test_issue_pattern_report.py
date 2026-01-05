import json

from scripts import issue_pattern_report as report


def test_build_report_with_patterns() -> None:
    corpus = {
        "generated_at": "2025-01-01T00:00:00Z",
        "criteria": {"min_completion_rate": 1.0},
        "patterns": [
            {
                "pattern_key": "tasks=1-2|acceptance=1-2|sections=why",
                "count": 3,
                "avg_task_count": 2.0,
                "avg_acceptance_count": 1.5,
                "issue_numbers": [10, 11, 12],
            }
        ],
        "successful_issues": [
            {
                "issue_number": 10,
                "pr_number": 101,
                "title": "Add tests for parser",
                "completion_rate": 1.0,
                "iteration_count": 2,
                "human_interventions": 0,
                "task_count": 2,
                "acceptance_count": 1,
            }
        ],
    }

    output = report.build_report(corpus, max_patterns=5, max_issues=5)

    assert "# Issue Pattern Report" in output
    assert "tasks=1-2|acceptance=1-2|sections=why" in output
    assert "Add tests for parser" in output


def test_main_writes_report(tmp_path, capsys) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps({"patterns": [], "successful_issues": []}),
        encoding="utf-8",
    )
    output_path = tmp_path / "report.md"

    result = report.main(
        ["--corpus-path", str(corpus_path), "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert output_path.exists()
    assert "Wrote issue pattern report to" in captured.out


def test_main_missing_corpus_returns_error(capsys) -> None:
    result = report.main(["--corpus-path", "missing.json"])

    captured = capsys.readouterr()
    assert result == 1
    assert "issue_pattern_report: corpus not found" in captured.err
