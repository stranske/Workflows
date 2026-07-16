from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools import llm_registry as registry


def _write_registry(path: Path, *, selected: str = "model-balanced") -> None:
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "model-frontier",
                        "lifecycle": "current",
                    },
                    {
                        "provider": "openai",
                        "model_id": "model-balanced",
                        "lifecycle": "current",
                    },
                ],
                "selections": [
                    {
                        "profile": "verifier-balanced",
                        "provider": "openai",
                        "model_id": selected,
                        "status": "approved",
                        "review_by": "2026-12-31",
                        "evidence_ids": ["benchmark-1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_slots(
    path: Path,
    *,
    model: str | None = None,
    profile: str = "verifier-balanced",
) -> None:
    slot = {
        "name": "slot1",
        "provider": "openai",
        "profile": profile,
    }
    if model:
        slot["model"] = model
    path.write_text(
        json.dumps({"slots": [slot]}),
        encoding="utf-8",
    )


def test_profile_selection_uses_explicit_decision_not_model_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert registry.select_model_for_profile(provider="openai") == "model-balanced"


def test_new_catalog_model_does_not_auto_promote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["models"].append(
        {"provider": "openai", "model_id": "model-new", "lifecycle": "current"}
    )
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert registry.select_model_for_profile(provider="openai") == "model-balanced"


def test_registry_decision_update_changes_slot_without_slot_edit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path)
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    before = registry.load_slot_config()
    _write_registry(registry_path, selected="model-frontier")
    after = registry.load_slot_config()

    assert before[0].model == "model-balanced"
    assert after[0].model == "model-frontier"
    assert "model" not in json.loads(slots_path.read_text())["slots"][0]


def test_legacy_slot_pin_is_honored_when_current_and_unblocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path, model="model-frontier", profile="")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config()[0].model == "model-frontier"
    assert registry.configured_model_for_provider("openai") == "model-frontier"


def test_unknown_explicit_profile_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path, profile="misspelled-profile")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    # A present slot config is an allowlist; an unresolved profile fails closed.
    assert registry.load_slot_config(github_default_model="fallback-github-model") == []
    assert registry.configured_model_for_provider("openai") == ""


def test_all_unusable_slot_entries_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path, profile="misspelled-profile")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config() == []


def test_empty_slot_config_does_not_broaden_to_default_providers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    slots_path.write_text(json.dumps({"slots": []}), encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config() == []
    assert registry.configured_model_for_provider("openai") == ""


def test_invalid_slot_config_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    slots_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config() == []
    assert registry.configured_model_for_provider("openai") == ""


def test_undecodable_explicit_slot_config_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    slots_path.write_bytes(b"\xff")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config() == []


def test_missing_explicit_slot_config_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(tmp_path / "missing-slots.json"))
    monkeypatch.setenv("LANGCHAIN_MODEL", "emergency-model")

    assert registry.load_slot_config() == []
    assert registry.resolve_slots() == []
    assert registry.configured_model_for_provider("openai") == ""


def test_invalid_registry_with_explicit_profile_slot_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    registry_path.write_text("{}", encoding="utf-8")
    _write_slots(slots_path)
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config(github_default_model="fallback-github-model") == []


def test_unresolved_explicit_slot_pin_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path, model="retired-model", profile="")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))

    assert registry.load_slot_config() == []
    assert registry.configured_model_for_provider("openai") == ""


def test_noncurrent_selected_model_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["models"][1]["lifecycle"] = "compatibility"
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert registry.select_model_for_profile(provider="openai") is None


def test_duplicate_profile_decisions_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    duplicate = dict(payload["selections"][0])
    duplicate["model_id"] = "model-frontier"
    payload["selections"].append(duplicate)
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert registry.select_model_for_profile(provider="openai") is None


def test_selection_without_evidence_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    _write_registry(registry_path)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["selections"][0]["evidence_ids"] = []
    registry_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))

    assert registry.select_model_for_profile(provider="openai") is None


def test_configured_model_honors_runtime_slot_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    registry_path = tmp_path / "registry.json"
    slots_path = tmp_path / "slots.json"
    _write_registry(registry_path)
    _write_slots(slots_path)
    monkeypatch.setenv(registry.ENV_MODEL_REGISTRY_CONFIG, str(registry_path))
    monkeypatch.setenv(registry.ENV_SLOT_CONFIG, str(slots_path))
    monkeypatch.setenv("LANGCHAIN_MODEL", "emergency-model")

    assert registry.configured_model_for_provider("openai") == "emergency-model"


def test_runtime_helpers_contain_no_model_version_literals() -> None:
    root = Path(__file__).resolve().parents[2]
    for relative in ("tools/llm_registry.py", "tools/llm_provider.py"):
        text = (root / relative).read_text(encoding="utf-8")
        assert "gpt-5." not in text
        assert "gpt-4" not in text
        assert "claude-sonnet-" not in text
        assert "codex-mini" not in text
