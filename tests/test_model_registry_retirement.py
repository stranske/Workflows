"""Validate retirement backup claims against a consumer's create-only slot config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NO_BACKUP_NOTE = (
    "Consumers without a capacity_backup block in config/llm_slots.json "
    "have no configured backup"
)
REPORTED_REASON = (
    "Owner decision 2026-10-31: GitHub Models is no longer used as a fallback. "
    "The verifier's third slot is the Muse capacity backup "
    "(config/llm_slots.json capacity_backup); LangChain tools fall back only "
    "between OpenAI and Anthropic."
)


def _validate_retirement_backups(registry: dict, slots: dict) -> None:
    """A backup claim needs a matching enabled config or an explicit absence note.

    Keep this source-data check local to the tests: the synced registry must be
    truthful even for consumers that never received the source's backup block.
    Named replacements must identify their provider and model for offline validation.
    """
    for entry in registry["selection_history"]:
        if entry.get("superseded_by") != "retired":
            continue
        reason = entry.get("supersede_reason", "")
        if "backup" not in reason.lower() or NO_BACKUP_NOTE in reason:
            continue
        backup = slots.get("capacity_backup")
        if (
            not isinstance(backup, dict)
            or backup.get("enabled") is not True
            or any(
                not isinstance(backup.get(field), str) or not backup[field].strip()
                for field in ("provider", "model", "base_url", "key_env")
            )
            or backup["provider"].lower() not in reason.lower()
            or backup["model"].lower() not in reason.lower()
        ):
            raise ValueError("retirement backup is not configured in config/llm_slots.json")


@pytest.fixture(params=[ROOT, ROOT / "templates/consumer-repo"], ids=["source", "template"])
def config_root(request) -> Path:
    """Exercise both delivered registry copies with their own create-only slots."""
    return request.param


@pytest.fixture
def registry(config_root: Path) -> dict:
    return json.loads((config_root / "config/model_registry.json").read_text(encoding="utf-8"))


@pytest.fixture
def slots(config_root: Path) -> dict:
    return json.loads((config_root / "config/llm_slots.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("has_backup", [False, True])
def test_registry_retirement_supports_create_only_consumer_slots(registry, slots, has_backup):
    if not has_backup:
        slots.pop("capacity_backup")
        retired = next(
            e
            for e in registry["selection_history"]
            if e.get("superseded_by") == "retired" and e["provider"] == "github-models"
        )
        assert NO_BACKUP_NOTE in retired["supersede_reason"]
    _validate_retirement_backups(registry, slots)


def test_reported_muse_replacement_without_consumer_backup_is_rejected(registry, slots):
    slots.pop("capacity_backup")
    retired = next(e for e in registry["selection_history"] if e.get("superseded_by") == "retired")
    retired["supersede_reason"] = REPORTED_REASON
    with pytest.raises(ValueError, match="retirement backup is not configured"):
        _validate_retirement_backups(registry, slots)


@pytest.mark.parametrize("defect", [None, "absent", "disabled", "wrong-model", "missing-url"])
def test_named_replacement_requires_matching_consumer_backup(registry, slots, defect):
    retired = next(e for e in registry["selection_history"] if e.get("superseded_by") == "retired")
    backup = slots["capacity_backup"]
    retired["supersede_reason"] = (
        f"Replacement capacity backup: {backup['provider']}/{backup['model']} "
        "(config/llm_slots.json capacity_backup)."
    )
    if defect == "absent":
        slots.pop("capacity_backup")
    elif defect == "disabled":
        backup["enabled"] = False
    elif defect == "wrong-model":
        backup["model"] = "another-model"
    elif defect == "missing-url":
        backup.pop("base_url")
    if defect is None:
        _validate_retirement_backups(registry, slots)
    else:
        with pytest.raises(ValueError, match="retirement backup is not configured"):
            _validate_retirement_backups(registry, slots)
