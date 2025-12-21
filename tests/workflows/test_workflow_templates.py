import json
from pathlib import Path

import yaml

TEMPLATE_DIR = Path(".github/workflow-templates")

TEMPLATES = {
    "python-ci": {
        "display_name": "Python CI (Workflows)",
        "reusable_workflow": "stranske/Workflows/.github/workflows/reusable-10-ci-python.yml@main",
    },
}


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_templates_present_with_metadata_files():
    assert TEMPLATE_DIR.exists(), "Missing .github/workflow-templates directory"

    for slug in TEMPLATES:
        workflow = TEMPLATE_DIR / f"{slug}.yml"
        metadata = TEMPLATE_DIR / f"{slug}.properties.json"
        assert workflow.exists(), f"Starter workflow missing: {workflow}"
        assert metadata.exists(), f"Metadata file missing for starter workflow: {metadata}"


def test_starter_template_metadata_matches_yaml():
    for slug, info in TEMPLATES.items():
        workflow = TEMPLATE_DIR / f"{slug}.yml"
        metadata = TEMPLATE_DIR / f"{slug}.properties.json"

        yaml_data = _read_yaml(workflow)
        props = _read_json(metadata)

        assert (
            yaml_data.get("name") == info["display_name"]
        ), f"Starter workflow name should match expected display name for {slug}"
        assert (
            props.get("name") == info["display_name"]
        ), f"Properties name should match template display name for {slug}"
        jobs = yaml_data.get("jobs") or {}
        python_ci = jobs.get("python-ci") or {}
        assert (
            python_ci.get("uses") == info["reusable_workflow"]
        ), f"Starter workflow should call the reusable workflow for {slug}"


def test_properties_files_include_required_keys_and_icon():
    icons_dir = TEMPLATE_DIR / "icons"
    assert icons_dir.exists(), "Icons directory missing for workflow templates"

    for slug in TEMPLATES:
        props = _read_json(TEMPLATE_DIR / f"{slug}.properties.json")

        for key in ("name", "description", "iconName", "categories", "filePatterns"):
            assert props.get(key), f"Expected {key} in properties for {slug}"

        assert (
            isinstance(props["categories"], list) and props["categories"]
        ), f"Categories should be a non-empty list for {slug}"
        assert (
            isinstance(props["filePatterns"], list) and props["filePatterns"]
        ), f"filePatterns should be a non-empty list for {slug}"

        icon_path = icons_dir / f"{props['iconName']}.svg"
        assert icon_path.exists(), f"Icon referenced by {slug} is missing: {icon_path}"


def test_trigger_configuration_is_present_for_python_ci():
    workflow = TEMPLATE_DIR / "python-ci.yml"
    yaml_data = _read_yaml(workflow)
    triggers = yaml_data.get("on") or {}

    for trigger in ("push", "pull_request", "workflow_dispatch"):
        assert trigger in triggers, f"{trigger} trigger missing from python CI starter workflow"
