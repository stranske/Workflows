from pathlib import Path


def test_model_eval_pilot_runs_as_importable_module() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/maint-78-model-evaluation-pilot.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("python -m tools.run_model_eval_pilot") == 1
    assert "python tools/run_model_eval_pilot.py" not in workflow
    assert "if [ ! -f pilot-results.json ]" in workflow
    assert "if-no-files-found: warn" in workflow
