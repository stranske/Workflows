import pytest
from tools.ensure_workflow_timeout_variables import (
    RepoVariableError,
    VariableSpec,
    build_timeout_variables,
    fetch_repo_variables,
    plan_variable_updates,
)


class FakeResponse:
    def __init__(self, status_code, payload, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if not self._responses:
            raise AssertionError("No more responses configured")
        return self._responses.pop(0)


def test_build_timeout_variables_defaults():
    variables = build_timeout_variables(45, 90)
    assert variables == [
        VariableSpec("WORKFLOW_TIMEOUT_DEFAULT", "45"),
        VariableSpec("WORKFLOW_TIMEOUT_EXTENDED", "90"),
    ]


def test_plan_variable_updates_detects_create_and_update():
    desired = [
        VariableSpec("WORKFLOW_TIMEOUT_DEFAULT", "45"),
        VariableSpec("WORKFLOW_TIMEOUT_EXTENDED", "90"),
    ]
    existing = {"WORKFLOW_TIMEOUT_DEFAULT": "30"}
    to_create, to_update = plan_variable_updates(desired, existing)
    assert to_create == [VariableSpec("WORKFLOW_TIMEOUT_EXTENDED", "90")]
    assert to_update == [VariableSpec("WORKFLOW_TIMEOUT_DEFAULT", "45")]


def test_fetch_repo_variables_filters_wanted_names():
    payload = {
        "variables": [
            {"name": "WORKFLOW_TIMEOUT_DEFAULT", "value": "45"},
            {"name": "SOMETHING_ELSE", "value": "1"},
        ]
    }
    session = FakeSession([FakeResponse(200, payload)])
    result = fetch_repo_variables(
        session,
        "octo/demo",
        ["WORKFLOW_TIMEOUT_DEFAULT", "WORKFLOW_TIMEOUT_EXTENDED"],
        api_root="https://api.github.com",
    )
    assert result == {"WORKFLOW_TIMEOUT_DEFAULT": "45"}


def test_fetch_repo_variables_raises_on_error():
    session = FakeSession([FakeResponse(403, {"message": "Forbidden"}, text="Forbidden")])
    with pytest.raises(RepoVariableError):
        fetch_repo_variables(
            session,
            "octo/demo",
            ["WORKFLOW_TIMEOUT_DEFAULT"],
            api_root="https://api.github.com",
        )
