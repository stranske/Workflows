from __future__ import annotations

import json
from pathlib import Path
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


def test_resolve_api_root_prefers_explicit_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert gate.resolve_api_root("https://api.example.com/") == "https://api.example.com"

    monkeypatch.setenv("GITHUB_API_URL", "https://enterprise.example.com/api/v3/")
    assert gate.resolve_api_root(None) == "https://enterprise.example.com/api/v3"

    monkeypatch.delenv("GITHUB_API_URL", raising=False)
    assert gate.resolve_api_root("") == gate.DEFAULT_API_ROOT


def test_state_from_status_payload_handles_contexts_and_strict() -> None:
    state = gate._state_from_status_payload(
        {"contexts": ["b", "a"], "strict": None},
        default_strict=True,
    )
    assert state.contexts == ["a", "b"]
    assert state.strict is None


def test_is_rate_limit_response_detects_exhaustion() -> None:
    assert gate._is_rate_limit_response(FakeResponse(status_code=429)) is True

    assert (
        gate._is_rate_limit_response(
            FakeResponse(status_code=403, headers={"X-RateLimit-Remaining": "0"})
        )
        is True
    )

    assert (
        gate._is_rate_limit_response(
            FakeResponse(status_code=403, json_data={"message": "Rate limit exceeded"})
        )
        is True
    )

    assert gate._is_rate_limit_response(FakeResponse(status_code=403)) is False


def test_retry_delay_seconds_prefers_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "RATE_LIMIT_BASE_DELAY", 1.0)
    monkeypatch.setattr(gate, "RATE_LIMIT_MIN_DELAY", 0.5)

    response = FakeResponse(headers={"Retry-After": "5"})
    assert gate._retry_delay_seconds(response, attempt=1) >= 5

    monkeypatch.setattr(gate.time, "time", lambda: 100.0)
    response = FakeResponse(headers={"X-RateLimit-Reset": "111"})
    assert gate._retry_delay_seconds(response, attempt=1) >= 11.0


def test_call_with_rate_limit_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(status_code=429, headers={"Retry-After": "0.1"}),
        FakeResponse(status_code=200),
    ]
    sleeps: list[float] = []

    def fake_call() -> FakeResponse:
        return responses.pop(0)

    monkeypatch.setattr(gate, "_sleep", lambda delay: sleeps.append(delay))

    response = gate._call_with_rate_limit_retry("fetching", fake_call)

    assert response.status_code == 200
    assert sleeps


def test_fetch_status_checks_uses_ruleset_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(get=lambda *args, **kwargs: FakeResponse(status_code=404))
    expected = gate.StatusCheckState(strict=True, contexts=["Gate / gate"])

    monkeypatch.setattr(gate, "_fetch_ruleset_status_checks", lambda *args, **kwargs: expected)

    assert (
        gate.fetch_status_checks(session, "octo/repo", "main", api_root="https://api.test")
        == expected
    )


def test_fetch_ruleset_status_checks_collects_contexts() -> None:
    rulesets = [
        {
            "id": 1,
            "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
        }
    ]
    ruleset_detail = {
        "rules": [
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": "Gate / gate"}],
                },
            }
        ]
    }

    def fake_get(url: str, timeout: int = 30) -> FakeResponse:
        if url.endswith("/rulesets"):
            return FakeResponse(status_code=200, json_data=rulesets)
        if url.endswith("/rulesets/1"):
            return FakeResponse(status_code=200, json_data=ruleset_detail)
        return FakeResponse(status_code=404)

    session = SimpleNamespace(get=fake_get)
    state = gate._fetch_ruleset_status_checks(
        session, "octo/repo", "main", api_root="https://api.test"
    )

    assert state is not None
    assert state.contexts == ["Gate / gate"]
    assert state.strict is True


def test_main_check_returns_nonzero_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def fake_fetch(*args, **kwargs):
        return gate.StatusCheckState(strict=False, contexts=[])

    monkeypatch.setattr(gate, "fetch_status_checks", fake_fetch)

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--check",
            "--context",
            "Gate / gate",
            "--context",
            "Health 45 Agents Guard / Enforce agents workflow protections",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Would add contexts" in captured.out
    assert "Would enable 'require branches to be up to date'." in captured.out


def test_main_apply_updates_and_writes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def fake_fetch(*args, **kwargs):
        return gate.StatusCheckState(strict=False, contexts=["Other / job"])

    def fake_update(*args, **kwargs):
        return gate.StatusCheckState(
            strict=True,
            contexts=[
                "Gate / gate",
                "Health 45 Agents Guard / Enforce agents workflow protections",
            ],
        )

    monkeypatch.setattr(gate, "fetch_status_checks", fake_fetch)
    monkeypatch.setattr(gate, "update_status_checks", fake_update)
    monkeypatch.setattr(gate, "_build_session", lambda token: SimpleNamespace())

    snapshot_path = tmp_path / "snapshot.json"

    exit_code = gate.main(
        [
            "--repo",
            "octo/repo",
            "--apply",
            "--snapshot",
            str(snapshot_path),
            "--context",
            "Gate / gate",
            "--context",
            "Health 45 Agents Guard / Enforce agents workflow protections",
        ]
    )

    assert exit_code == 0
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["changes_applied"] is True
    assert payload["after"]["strict"] is True
