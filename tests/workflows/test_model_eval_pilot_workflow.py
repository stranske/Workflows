from pathlib import Path

import yaml


def test_model_eval_pilot_runs_as_importable_module() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/maint-78-model-evaluation-pilot.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["pilot"]["steps"]
    pilot = next(step for step in steps if step.get("name") == "Run paired 30-case pilot")
    summary = next(step for step in steps if step.get("name") == "Summarize pilot")
    upload = next(step for step in steps if "actions/upload-artifact@" in step.get("uses", ""))

    assert pilot["run"].count("python -m tools.run_model_eval_pilot") == 1
    assert "python tools/run_model_eval_pilot.py" not in pilot["run"]
    assert summary["if"] == "always()"
    assert "if [ ! -f pilot-results.json ]" in summary["run"]
    assert upload["if"] == "always()"
    assert upload["with"]["if-no-files-found"] == "warn"
