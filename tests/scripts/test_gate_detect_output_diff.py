import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import gate_detect_output_diff as diff

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _minimal_detect_workflow(outputs: str, steps: str = "      - id: classify\n") -> str:
    return f"""
jobs:
  detect:
    outputs:
{outputs}
    steps:
{steps}"""


def test_output_refs_extracts_multiple_step_output_references() -> None:
    expression = (
        "${{ steps.detect.outputs.doc_only == 'true' && "
        "steps.path-classifier.outputs.affected_consumers != '' && "
        "steps.reason_builder.outputs.classification_rationale }}"
    )

    assert diff._output_refs(expression) == [
        ("detect", "doc_only"),
        ("path-classifier", "affected_consumers"),
        ("reason_builder", "classification_rationale"),
    ]


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


def test_compare_detect_outputs_reports_removed_keys_and_counts(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
      run_core: ${{ steps.classify.outputs.run_core }}
      reason: ${{ steps.classify.outputs.reason }}
"""),
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
"""),
    )

    report = diff.compare_gate_detect_outputs(candidate, baseline)

    assert report["candidate_output_count"] == 1
    assert report["baseline_output_count"] == 3
    assert report["removed_outputs_vs_baseline"] == ["reason", "run_core"]
    assert report["added_outputs_vs_baseline"] == []


def test_compare_detect_outputs_treats_missing_and_non_mapping_outputs_as_empty(
    tmp_path: Path,
) -> None:
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
    missing_outputs = _write(
        tmp_path / "missing-outputs.yml",
        """
jobs:
  detect:
    steps:
      - id: classify
        run: echo ok
""",
    )
    non_mapping_outputs = _write(
        tmp_path / "non-mapping-outputs.yml",
        """
jobs:
  detect:
    outputs:
      - doc_only
      - run_core
    steps:
      - id: classify
        run: echo ok
""",
    )

    missing_report = diff.compare_gate_detect_outputs(missing_outputs, baseline)
    non_mapping_report = diff.compare_gate_detect_outputs(non_mapping_outputs, baseline)

    for report in (missing_report, non_mapping_report):
        assert report["candidate_output_count"] == 0
        assert report["baseline_output_count"] == 2
        assert report["removed_outputs_vs_baseline"] == ["doc_only", "run_core"]
        assert report["added_outputs_vs_baseline"] == []
        assert report["invalid_step_output_references"] == {}


def test_compare_detect_outputs_accepts_underscore_and_hyphen_step_ids(
    tmp_path: Path,
) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        """
jobs:
  detect:
    outputs:
      affected_consumers: ${{ steps.path-classifier.outputs.affected_consumers }}
    steps:
      - id: path-classifier
        run: echo ok
""",
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        """
jobs:
  detect:
    outputs:
      affected_consumers: ${{ steps.path-classifier.outputs.affected_consumers }}
      classification_rationale: ${{ steps.classify_paths.outputs.classification-rationale }}
      stale_output: ${{ steps.missing-step.outputs.value }}
    steps:
      - id: path-classifier
        run: echo ok
      - id: classify_paths
        run: echo ok
""",
    )

    report = diff.compare_gate_detect_outputs(candidate, baseline)

    assert report["candidate_output_count"] == 3
    assert report["baseline_output_count"] == 1
    assert report["candidate_step_ids"] == ["classify_paths", "path-classifier"]
    assert report["added_outputs_vs_baseline"] == [
        "classification_rationale",
        "stale_output",
    ]
    assert report["invalid_step_output_references"] == {"stale_output": ["missing-step"]}


@pytest.mark.parametrize(
    ("candidate_body", "message"),
    [
        ("name: Gate\n", "workflow missing jobs mapping"),
        ("jobs:\n  build:\n    steps: []\n", "workflow missing jobs.detect"),
    ],
)
def test_compare_detect_outputs_rejects_malformed_workflow_shapes(
    tmp_path: Path, candidate_body: str, message: str
) -> None:
    candidate = _write(tmp_path / "candidate.yml", candidate_body)
    baseline = _write(
        tmp_path / "baseline.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
"""),
    )

    with pytest.raises(ValueError, match=message):
        diff.compare_gate_detect_outputs(candidate, baseline)


def test_cli_exits_nonzero_and_reports_invalid_step_output_references(tmp_path: Path) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
"""),
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
      affected_consumers: ${{ steps.path_classifier.outputs.affected_consumers }}
"""),
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/gate_detect_output_diff.py",
            "--candidate",
            str(candidate),
            "--baseline",
            str(baseline),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["invalid_step_output_references"] == {"affected_consumers": ["path_classifier"]}


def test_main_preserves_json_report_shape_for_invalid_refs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = _write(
        tmp_path / "baseline.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
"""),
    )
    candidate = _write(
        tmp_path / "candidate.yml",
        _minimal_detect_workflow("""
      doc_only: ${{ steps.classify.outputs.doc_only }}
      affected_consumers: ${{ steps.path_classifier.outputs.affected_consumers }}
"""),
    )

    exit_code = diff.main(["--candidate", str(candidate), "--baseline", str(baseline)])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 1
    assert report["candidate_path"] == str(candidate)
    assert report["baseline_path"] == str(baseline)
    assert report["invalid_step_output_references"] == {"affected_consumers": ["path_classifier"]}
    assert {
        "candidate_output_count",
        "baseline_output_count",
        "added_outputs_vs_baseline",
        "removed_outputs_vs_baseline",
        "candidate_step_ids",
    } <= set(report)


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
