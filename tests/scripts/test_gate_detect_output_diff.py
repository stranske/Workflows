from pathlib import Path

from scripts import gate_detect_output_diff as diff

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_compare_detect_outputs_reports_added_keys_without_invalid_refs(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        """
jobs:
  detect:
    outputs:
      doc_only: ${{ steps.classify.outputs.doc_only }}
      run_core: ${{ steps.classify.outputs.run_core }}
    steps:
      - id: classify
        run: echo ok
""",
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        """
jobs:
  detect:
    outputs:
      doc_only: ${{ steps.classify.outputs.doc_only }}
      run_core: ${{ steps.classify.outputs.run_core }}
      classification_rationale: ${{ steps.classify.outputs.classification_rationale }}
    steps:
      - id: classify
        run: echo ok
""",
    )

    report = diff.compare_gate_detect_outputs(candidate, baseline)

    assert report["added_outputs_vs_baseline"] == ["classification_rationale"]
    assert report["invalid_step_output_references"] == {}


def test_compare_detect_outputs_flags_missing_step_ids(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        """
jobs:
  detect:
    outputs:
      doc_only: ${{ steps.classify.outputs.doc_only }}
    steps:
      - id: classify
        run: echo ok
""",
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        """
jobs:
  detect:
    outputs:
      doc_only: ${{ steps.classify.outputs.doc_only }}
      affected_consumers: ${{ steps.path_classifier.outputs.affected_consumers }}
    steps:
      - id: classify
        run: echo ok
""",
    )

    report = diff.compare_gate_detect_outputs(candidate, baseline)

    assert report["invalid_step_output_references"] == {"affected_consumers": ["path_classifier"]}


def test_template_gate_detect_outputs_expand_known_green_minimal_baseline() -> None:
    candidate = REPO_ROOT / "templates/consumer-repo/.github/workflows/pr-00-gate.yml"
    baseline = REPO_ROOT / "tests/fixtures/workflows/pr-00-gate-known-green-minimal.yml"

    report = diff.compare_gate_detect_outputs(candidate, baseline)

    candidate_outputs = set(report["added_outputs_vs_baseline"]) | {
        "doc_only",
        "run_core",
        "reason",
    }
    assert {
        "doc_only",
        "run_core",
        "is_template_change",
        "is_test_only",
        "affected_consumers",
        "classification_rationale",
    } - candidate_outputs == set()
