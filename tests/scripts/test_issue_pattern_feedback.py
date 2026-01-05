import json

from scripts import issue_pattern_feedback as feedback


def test_build_feedback_with_patterns() -> None:
    corpus = {
        "successful_issues": [
            {
                "task_count": 3,
                "acceptance_count": 2,
                "sections": {
                    "why": True,
                    "scope": True,
                    "non_goals": False,
                    "implementation": True,
                },
            },
            {
                "task_count": 4,
                "acceptance_count": 1,
                "sections": {
                    "why": True,
                    "scope": False,
                    "non_goals": True,
                    "implementation": True,
                },
            },
        ],
        "patterns": [
            {
                "pattern_key": "tasks=3-5|acceptance=1-2|sections=why,scope,implementation",
                "count": 2,
                "avg_task_count": 3.5,
                "avg_acceptance_count": 1.5,
            }
        ],
    }

    output = feedback.build_feedback(corpus)

    assert "Successful issue sample size: 2" in output
    assert "Typical task count" in output
    assert "Top patterns" in output
    assert "tasks=3-5" in output


def test_main_writes_feedback(tmp_path, capsys) -> None:
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "successful_issues": [
                    {
                        "task_count": 1,
                        "acceptance_count": 1,
                        "sections": {"why": True, "scope": True},
                    }
                ],
                "patterns": [],
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "feedback.md"

    result = feedback.main(["--corpus-path", str(corpus_path), "--output", str(output_path)])

    captured = capsys.readouterr()
    assert result == 0
    assert output_path.exists()
    assert "Wrote issue format feedback to" in captured.out


def test_main_missing_corpus_returns_error(capsys) -> None:
    result = feedback.main(["--corpus-path", "missing.json"])

    captured = capsys.readouterr()
    assert result == 1
    assert "issue_pattern_feedback: corpus not found" in captured.err
