import pytest

from tests._autofix_diag import DiagnosticsRecorder, autofix_recorder  # noqa: F401


@pytest.fixture
def llm_env_sentinel(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "GITHUB_REPOSITORY": "sentinel/repo",
        "GITHUB_RUN_ID": "run-777",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values
