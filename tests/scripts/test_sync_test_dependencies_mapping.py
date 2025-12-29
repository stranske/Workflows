from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pptx_maps_to_python_pptx_in_repo_script():
    module = _load_module(
        "sync_test_dependencies_repo",
        Path("scripts/sync_test_dependencies.py"),
    )

    assert module.MODULE_TO_PACKAGE["pptx"] == "python-pptx"


def test_pptx_maps_to_python_pptx_in_consumer_template():
    module = _load_module(
        "sync_test_dependencies_consumer_template",
        Path("templates/consumer-repo/scripts/sync_test_dependencies.py"),
    )

    assert module.MODULE_TO_PACKAGE["pptx"] == "python-pptx"
