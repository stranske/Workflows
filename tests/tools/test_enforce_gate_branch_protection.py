from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from tools import enforce_gate_branch_protection as gate


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        content: bytes | None = b"{}",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        self.content = content if content is not None else b""

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def get(self, url: str, *, timeout: int) -> FakeResponse:
        self.calls.append(("GET", url))
        return self.responses.pop(0)


def test_resolve_api_root_prefers_explicit_env_and_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert gate.resolve_api_root(" https://github.example.com/api/v3/ ") == (
        "https://github.example.com/api/v3"
    )
    assert gate.resolve_api_root("   ") == gate.DEFAULT_API_ROOT

    monkeypatch.setenv("GITHUB_API_URL", "https://enterprise.example/api/v3///")
    assert gate.resolve_api_root(None) == "https://enterprise.example/api/v3"

    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    assert gate.resolve_api_root(None) == gate.DEFAULT_API_ROOT


def test_status_and_branch_urls_use_normalized_api_root() -> None:
    api_root = gate.resolve_api_root("https://github.example.com/api/v3/")

    assert gate._status_checks_url("octo/repo", "main", api_root=api_root) == (
        "https://github.example.com/api/v3/repos/octo/repo/branches/main"
        "/protection/required_status_checks"
    )
    assert gate._branch_url("octo/repo", "release/v1", api_root=api_root) == (
        "https://github.example.com/api/v3/repos/octo/repo/branches/release/v1"
    )


def test_state_from_status_payload_normalizes_contexts_and_strict() -> None:
    state = gate._state_from_status_payload(
        {"contexts": ["zeta", 3, "alpha"]},
        default_strict=None,
    )
    assert state == gate.StatusCheckState(strict=None, contexts=["3", "alpha", "zeta"])

    state = gate._state_from_status_payload(
        {"contexts": "Gate / gate", "strict": 0},
        default_strict=True,
    )
    assert state == gate.StatusCheckState(strict=False, contexts=[])


def test_response_message_prefers_json_message_and_falls_back_to_text() -> None:
    assert (
        gate._response_message(FakeResponse(json_data={"message": "secondary rate limit"}))
        == "secondary rate limit"
    )
    assert (
        gate._response_message(FakeResponse(json_data={"message": "   "}, text="  plain error  "))
        == "plain error"
    )
    assert (
        gate._response_message(FakeResponse(json_data=ValueError("not json"), text=" raw "))
        == "raw"
    )


def test_is_rate_limit_response_detects_status_headers_and_messages() -> None:
    assert gate._is_rate_limit_response(FakeResponse(status_code=429)) is True
    assert (
        gate._is_rate_limit_response(
            FakeResponse(status_code=403, headers={"X-RateLimit-Remaining": "0"})
        )
        is True
    )
    assert (
        gate._is_rate_limit_response(
            FakeResponse(
                status_code=403,
                headers={"x-ratelimit-remaining": "not-a-number"},
                json_data={"message": "secondary Rate Limit reached"},
            )
        )
        is True
    )
    assert (
        gate._is_rate_limit_response(
            FakeResponse(status_code=403, headers={"X-RateLimit-Remaining": "1"})
        )
        is False
    )
    assert gate._is_rate_limit_response(FakeResponse(status_code=500)) is False


def test_retry_delay_seconds_uses_retry_after_reset_and_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate, "RATE_LIMIT_BASE_DELAY", 2.0)
    monkeypatch.setattr(gate, "RATE_LIMIT_MIN_DELAY", 1.0)

    assert (
        gate._retry_delay_seconds(
            FakeResponse(headers={"Retry-After": "7"}),
            attempt=1,
        )
        == 7
    )
    assert (
        gate._retry_delay_seconds(
            FakeResponse(headers={"Retry-After": "bad"}),
            attempt=1,
        )
        == 2
    )

    monkeypatch.setattr(gate.time, "time", lambda: 100.0)
    assert gate._retry_delay_seconds(
        FakeResponse(headers={"x-ratelimit-reset": "105"}),
        attempt=1,
    ) == pytest.approx(5.5)

    monkeypatch.setattr(gate, "RATE_LIMIT_BASE_DELAY", 0.1)
    monkeypatch.setattr(gate, "RATE_LIMIT_MIN_DELAY", 1.5)
    assert gate._retry_delay_seconds(FakeResponse(), attempt=1) == 1.5


def test_call_with_rate_limit_retry_returns_success_after_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            FakeResponse(status_code=429, headers={"Retry-After": "3"}),
            FakeResponse(status_code=200, json_data={"ok": True}),
        ]
    )
    sleeps: list[float] = []

    monkeypatch.setattr(gate, "RATE_LIMIT_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(gate, "_sleep", sleeps.append)

    response = gate._call_with_rate_limit_retry(
        "fetching guard state",
        lambda: session.get("https://api.example.test/repos/octo/repo", timeout=30),
    )

    assert response.status_code == 200
    assert sleeps == [3]
    assert session.calls == [
        ("GET", "https://api.example.test/repos/octo/repo"),
        ("GET", "https://api.example.test/repos/octo/repo"),
    ]


def test_call_with_rate_limit_retry_raises_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession(
        [
            FakeResponse(status_code=429, json_data={"message": "slow down"}),
            FakeResponse(status_code=403, headers={"X-RateLimit-Remaining": "0"}),
        ]
    )
    sleeps: list[float] = []

    monkeypatch.setattr(gate, "RATE_LIMIT_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(gate, "RATE_LIMIT_BASE_DELAY", 0.5)
    monkeypatch.setattr(gate, "RATE_LIMIT_MIN_DELAY", 0.5)
    monkeypatch.setattr(gate, "_sleep", sleeps.append)

    with pytest.raises(gate.BranchProtectionError) as exc_info:
        gate._call_with_rate_limit_retry(
            "fetching guard state",
            lambda: session.get("https://api.example.test/repos/octo/repo", timeout=30),
        )

    assert sleeps == [0.5]
    assert "exhausted 2 attempts" in str(exc_info.value)
    assert "Last response: 403" in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"protection": None},
        {"protection": {"enabled": False}},
        {"protection": {"enabled": True}},
        {"protection": {"enabled": True, "required_status_checks": None}},
    ],
)
def test_state_from_branch_payload_raises_for_disabled_or_missing_protection(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(gate.BranchProtectionMissingError):
        gate._state_from_branch_payload(payload)


def test_state_from_branch_payload_uses_required_status_checks() -> None:
    state = gate._state_from_branch_payload(
        {
            "protection": {
                "enabled": True,
                "required_status_checks": {
                    "contexts": ["Health 45 Agents Guard / guard", "Gate / gate"],
                },
            }
        }
    )

    assert state == gate.StatusCheckState(
        strict=None,
        contexts=["Gate / gate", "Health 45 Agents Guard / guard"],
    )


def test_state_from_branch_payload_preserves_explicit_strict_value() -> None:
    state = gate._state_from_branch_payload(
        {
            "protection": {
                "enabled": True,
                "required_status_checks": {
                    "strict": False,
                    "contexts": ["Gate / gate"],
                },
            }
        }
    )

    assert state == gate.StatusCheckState(strict=False, contexts=["Gate / gate"])


def test_allow_non_strict_accepts_a_deliberately_non_strict_policy(monkeypatch, capsys):
    """A non-strict ruleset is not drift when the reviewed policy is non-strict."""
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        gate,
        "fetch_status_checks",
        lambda *a, **k: gate.StatusCheckState(strict=False, contexts=["summary"]),
    )
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--check",
            "--allow-non-strict",
            "--no-clean",
            "--context",
            "summary",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "No changes required." in out
    assert "Desired 'require up to date': False" in out


def test_snapshot_desired_strict_tracks_allow_non_strict(monkeypatch, tmp_path):
    """The health artifact must not claim strict enforcement --apply would not create."""
    import json

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        gate,
        "fetch_status_checks",
        lambda *a, **k: gate.StatusCheckState(strict=False, contexts=["summary"]),
    )
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())
    snapshot_path = tmp_path / "snapshot.json"

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--check",
            "--allow-non-strict",
            "--no-clean",
            "--context",
            "summary",
            "--snapshot",
            str(snapshot_path),
        ]
    )

    snapshot = json.loads(snapshot_path.read_text())
    assert exit_code == 0
    assert snapshot["desired"]["strict"] is False


def test_allow_non_strict_snapshot_keeps_already_strict_as_accepted_target(monkeypatch, tmp_path):
    """Already-strict + --allow-non-strict must not report a True→False 'In sync' target."""
    import json

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        gate,
        "fetch_status_checks",
        lambda *a, **k: gate.StatusCheckState(strict=True, contexts=["summary"]),
    )
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())
    snapshot_path = tmp_path / "snapshot.json"

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--check",
            "--allow-non-strict",
            "--no-clean",
            "--context",
            "summary",
            "--snapshot",
            str(snapshot_path),
        ]
    )

    snapshot = json.loads(snapshot_path.read_text())
    assert exit_code == 0
    assert snapshot["changes_required"] is False
    assert snapshot["current"]["strict"] is True
    assert snapshot["desired"]["strict"] is True


def test_fetch_error_snapshot_under_allow_non_strict_records_non_strict_desired(
    monkeypatch, tmp_path
):
    """Error-path snapshots must keep desired.strict=False under --allow-non-strict."""
    import json

    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def _raise(*_a, **_k):
        raise gate.BranchProtectionError("status checks unavailable")

    monkeypatch.setattr(gate, "fetch_status_checks", _raise)
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())
    snapshot_path = tmp_path / "snapshot.json"

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--check",
            "--allow-non-strict",
            "--no-clean",
            "--context",
            "summary",
            "--snapshot",
            str(snapshot_path),
        ]
    )

    snapshot = json.loads(snapshot_path.read_text())
    assert exit_code == 1
    assert snapshot["error"] == "status checks unavailable"
    assert snapshot["desired"]["strict"] is False


def test_apply_allow_non_strict_preserves_already_strict_during_context_drift(
    monkeypatch, tmp_path
):
    """Context updates under --allow-non-strict must not disable an already-strict policy."""
    import json

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        gate,
        "fetch_status_checks",
        lambda *a, **k: gate.StatusCheckState(strict=True, contexts=["summary"]),
    )
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())
    captured: dict[str, Any] = {}

    def _update(_session, _repo, _branch, *, contexts, strict, api_root=None):
        captured["contexts"] = list(contexts)
        captured["strict"] = strict
        return gate.StatusCheckState(strict=strict, contexts=list(contexts))

    monkeypatch.setattr(gate, "update_status_checks", _update)
    snapshot_path = tmp_path / "snapshot.json"

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--apply",
            "--allow-non-strict",
            "--no-clean",
            "--context",
            "Gate / gate",
            "--snapshot",
            str(snapshot_path),
        ]
    )

    snapshot = json.loads(snapshot_path.read_text())
    assert exit_code == 0
    assert captured["strict"] is True
    assert "Gate / gate" in captured["contexts"]
    assert snapshot["desired"]["strict"] is True
    assert snapshot["after"]["strict"] is True


def test_without_allow_non_strict_a_non_strict_policy_is_still_drift(monkeypatch, capsys):
    """The default is unchanged: non-strict counts as drift unless opted out."""
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(
        gate,
        "fetch_status_checks",
        lambda *a, **k: gate.StatusCheckState(strict=False, contexts=["summary"]),
    )
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())

    exit_code = gate.main(["--repo", "octo/repo", "--check", "--no-clean", "--context", "summary"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Would enable 'require branches to be up to date'." in out


def test_allow_non_strict_conflicts_with_require_strict(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    with pytest.raises(SystemExit):
        gate.main(["--repo", "octo/repo", "--check", "--allow-non-strict", "--require-strict"])
