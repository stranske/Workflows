from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_ds_streamlit() -> ModuleType:
    path = Path("templates/consumer-repo/design-system/ds_streamlit.py")
    spec = importlib.util.spec_from_file_location("ds_streamlit_template", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ds_streamlit_import_does_not_require_streamlit() -> None:
    module = _load_ds_streamlit()

    assert module.availability_badge("Ready") == " · Ready"


def test_humanize_id_skips_opaque_uuid_and_hash_segments() -> None:
    module = _load_ds_streamlit()

    assert module.humanize_id("fund:large-cap-growth") == "large cap growth"
    assert module.humanize_id("fund:550e8400-e29b-41d4-a716-446655440000") == "fund"
    assert module.humanize_id("550e8400-e29b-41d4-a716-446655440000") == "item"
    assert module.humanize_id("run:e29b-41d4-a716") == "run"
    assert module.humanize_id("portfolio:de0849c19ac81e04") == "portfolio"
