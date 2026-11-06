import pytest
from tools import ensure_workflow_timeout_variables as timeout_variables
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


class UpdatingFakeSession(FakeSession):
    def __init__(self, responses):
        super().__init__(responses)
        self.posts = []
        self.patches = []

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json, timeout))
        return self._responses.pop(0)

    def patch(self, url, json=None, timeout=None):
        self.patches.append((url, json, timeout))
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


def test_configuration_helpers_resolve_environment_and_response_messages(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", " https://example.test/api/ ")
    monkeypatch.setenv("GITHUB_TOKEN", "environment-token")
    monkeypatch.setenv("GH_TOKEN", "fallback-token")
    assert timeout_variables.resolve_api_root() == "https://example.test/api"
    assert timeout_variables.resolve_api_root(" https://override.test/ ") == "https://override.test"
    assert timeout_variables.require_token(" explicit-token ") == "explicit-token"
    assert timeout_variables.require_token("   ") == "environment-token"
    assert timeout_variables._variables_url("octo/demo", api_root="https://api.test") == (
        "https://api.test/repos/octo/demo/actions/variables"
    )
    assert timeout_variables._variable_url("octo/demo", "THING", api_root="https://api.test") == (
        "https://api.test/repos/octo/demo/actions/variables/THING"
    )
    assert (
        timeout_variables._response_message(FakeResponse(400, {"message": " details "}))
        == " details "
    )


def test_configuration_helpers_handle_empty_roots_missing_tokens_and_invalid_json(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", "   ")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert timeout_variables.resolve_api_root() == timeout_variables.DEFAULT_API_ROOT
    with pytest.raises(RepoVariableError, match="GITHUB_TOKEN"):
        timeout_variables.require_token()

    response = FakeResponse(500, None, text=" response text ")
    response.json = lambda: (_ for _ in ()).throw(ValueError("not json"))
    assert timeout_variables._response_message(response) == "response text"


def test_build_session_sets_expected_headers(monkeypatch):
    class Session:
        def __init__(self):
            self.headers = {}

    monkeypatch.setattr(timeout_variables.requests, "Session", Session)
    session = timeout_variables._build_session("secret")
    assert session.headers == {
        "Authorization": "Bearer secret",
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflows-timeout-variables",
    }


def test_fetch_repo_variables_handles_empty_names_pagination_and_missing_values():
    assert (
        timeout_variables.fetch_repo_variables(
            FakeSession([]), "octo/demo", [], api_root="https://api.test"
        )
        == {}
    )
    first_page = [{"name": "IGNORED", "value": "1"}] * 98 + [
        {"name": "WORKFLOW_TIMEOUT_DEFAULT", "value": None},
        {"name": " ", "value": "ignored"},
    ]
    second_page = [{"name": "WORKFLOW_TIMEOUT_EXTENDED", "value": 90}]
    session = FakeSession(
        [
            FakeResponse(200, {"variables": first_page}),
            FakeResponse(200, {"variables": second_page}),
        ]
    )
    assert timeout_variables.fetch_repo_variables(
        session,
        "octo/demo",
        ["WORKFLOW_TIMEOUT_DEFAULT", "WORKFLOW_TIMEOUT_EXTENDED"],
        api_root="https://api.test",
    ) == {"WORKFLOW_TIMEOUT_EXTENDED": "90"}
    assert [call[1]["page"] for call in session.calls] == [1, 2]


def test_apply_and_describe_variable_updates_cover_success_and_errors():
    create = VariableSpec("CREATE", "45")
    update = VariableSpec("UPDATE", "90")
    session = UpdatingFakeSession([FakeResponse(201, {}), FakeResponse(204, {})])
    timeout_variables.apply_variable_updates(
        session,
        "octo/demo",
        api_root="https://api.test",
        to_create=[create],
        to_update=[update],
    )
    assert session.posts == [
        (
            "https://api.test/repos/octo/demo/actions/variables",
            {"name": "CREATE", "value": "45"},
            30,
        )
    ]
    assert session.patches == [
        (
            "https://api.test/repos/octo/demo/actions/variables/UPDATE",
            {"name": "UPDATE", "value": "90"},
            30,
        )
    ]
    assert timeout_variables.describe_plan([create], [update]) == [
        "create CREATE=45",
        "update UPDATE=90",
    ]

    with pytest.raises(RepoVariableError, match="Failed to create"):
        timeout_variables.apply_variable_updates(
            UpdatingFakeSession([FakeResponse(400, {"message": "nope"})]),
            "octo/demo",
            api_root="https://api.test",
            to_create=[create],
            to_update=[],
        )
    with pytest.raises(RepoVariableError, match="Failed to update"):
        timeout_variables.apply_variable_updates(
            UpdatingFakeSession([FakeResponse(500, {"message": "nope"})]),
            "octo/demo",
            api_root="https://api.test",
            to_create=[],
            to_update=[update],
        )


def test_main_reports_plans_applies_updates_and_handles_api_errors(monkeypatch, capsys):
    monkeypatch.setattr(timeout_variables, "require_token", lambda explicit: "token")
    monkeypatch.setattr(timeout_variables, "_build_session", lambda token: object())
    monkeypatch.setattr(
        timeout_variables,
        "fetch_repo_variables",
        lambda *args, **kwargs: {"WORKFLOW_TIMEOUT_DEFAULT": "45"},
    )
    assert timeout_variables.main(["--repo", "octo/demo", "--check"]) == 1
    assert "create WORKFLOW_TIMEOUT_EXTENDED=90" in capsys.readouterr().out

    applied = []
    monkeypatch.setattr(
        timeout_variables, "apply_variable_updates", lambda *args, **kwargs: applied.append(kwargs)
    )
    assert timeout_variables.main(["--repo", "octo/demo", "--apply"]) == 0
    assert applied and applied[0]["to_create"] == [VariableSpec("WORKFLOW_TIMEOUT_EXTENDED", "90")]
    assert "Updates applied." in capsys.readouterr().out

    monkeypatch.setattr(
        timeout_variables,
        "fetch_repo_variables",
        lambda *args, **kwargs: {
            "WORKFLOW_TIMEOUT_DEFAULT": "45",
            "WORKFLOW_TIMEOUT_EXTENDED": "90",
        },
    )
    assert timeout_variables.main(["--repo", "octo/demo"]) == 0
    assert "No changes required." in capsys.readouterr().out

    monkeypatch.setattr(
        timeout_variables,
        "require_token",
        lambda explicit: (_ for _ in ()).throw(RepoVariableError("denied")),
    )
    assert timeout_variables.main(["--repo", "octo/demo"]) == 2
    assert "ERROR: denied" in capsys.readouterr().err


def test_main_rejects_invalid_argument_combinations_and_missing_repo(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    with pytest.raises(SystemExit, match="2"):
        timeout_variables.main(["--apply", "--check", "--repo", "octo/demo"])
    with pytest.raises(SystemExit, match="2"):
        timeout_variables.main([])
