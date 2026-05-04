import json

import pytest
from scripts import state_fingerprint


class MemoryStorage:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.writes: list[str] = []

    def read_fingerprint(self, workflow_name: str) -> str | None:
        return state_fingerprint._extract_hash(self.value, workflow_name)

    def write_fingerprint(self, workflow_name: str, fingerprint_hash: str) -> None:
        self.value = state_fingerprint._build_marker(workflow_name, fingerprint_hash)
        self.writes.append(fingerprint_hash)


def test_compute_fingerprint_canonicalizes_key_order() -> None:
    first = state_fingerprint.compute_fingerprint("wf", {"b": 2, "a": {"d": 4, "c": 3}})
    second = state_fingerprint.compute_fingerprint("wf", {"a": {"c": 3, "d": 4}, "b": 2})

    assert first == second


def test_compare_detects_changed_inputs() -> None:
    prior = state_fingerprint.compute_fingerprint("wf", {"head_sha": "old"})
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "new"}, storage)

    assert decision.should_run is True
    assert decision.reason == "fingerprint-changed"
    assert decision.prior_hash == prior
    assert decision.current_hash != prior


def test_compare_skips_when_state_is_unchanged() -> None:
    current = {"head_sha": "abc", "labels": ["autofix"]}
    prior = state_fingerprint.compute_fingerprint("wf", current)
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    decision = state_fingerprint.compare_fingerprint("wf", current, storage)

    assert decision.should_run is False
    assert decision.reason == "fingerprint-match"
    assert decision.prior_hash == decision.current_hash


def test_missing_marker_is_first_run_behavior() -> None:
    storage = MemoryStorage()

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "abc"}, storage)

    assert decision.should_run is True
    assert decision.reason == "no-prior-fingerprint"
    assert decision.prior_hash is None


def test_warning_mode_bypasses_skip_and_logs_delta(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    current = {"head_sha": "abc"}
    prior = state_fingerprint.compute_fingerprint("wf", current)
    storage = MemoryStorage(state_fingerprint._build_marker("wf", prior))

    monkeypatch.setattr(state_fingerprint, "_storage_from_name", lambda _name, _workflow: storage)

    exit_code = state_fingerprint.main(
        [
            "compare",
            "--workflow",
            "wf",
            "--inputs",
            json.dumps(current),
            "--storage",
            "pr-comment",
            "--mode",
            "warning",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "state fingerprint warning mode" in captured.err
    outputs = json.loads(captured.out)
    assert outputs["should_run"] == "true"
    assert outputs["reason"] == "warning-mode:fingerprint-match"
    assert storage.writes == [prior]


def test_malformed_prior_marker_is_tolerated() -> None:
    storage = MemoryStorage('<!-- fingerprint:wf:v1 {"hash": -->')

    decision = state_fingerprint.compare_fingerprint("wf", {"head_sha": "abc"}, storage)

    assert decision.should_run is True
    assert decision.reason == "no-prior-fingerprint"
    assert decision.prior_hash is None
