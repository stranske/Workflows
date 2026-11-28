"""Isolate the deliberate-break suite's child pytest on xdist workers."""

import pytest


@pytest.fixture(autouse=True)
def isolate_deliberate_break_worker_subprocesses(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if request.node.path.name == "test_check_deliberate_break.py" and hasattr(
        request.config, "workerinput"
    ):
        # These child pytest runs use synthetic conftests. Leave the archived
        # serial comparison's plugin environment intact.
        monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
