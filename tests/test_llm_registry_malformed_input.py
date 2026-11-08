"""`llm_registry` against malformed configuration — the branches that decide which model runs.

Ranked third in this repository by `escaped_defect_priority` (20 fix commits, 23 churn) and 22
statements unexercised, every one of them a malformed-input path.

That matters more here than the count suggests. This module resolves the model an agent executes,
and its own comments state a fail-closed contract:

    An explicit slot config is an execution allowlist, including when its path is missing or
    malformed. Never broaden execution because a configured allowlist cannot be read.

A defect in these branches does not raise. It returns a plausible list, and the fleet runs a model
nobody allowed — so the failure is silent by construction and the contract was never tested.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest
from tools import llm_registry


@pytest.fixture()
def registry_at(tmp_path, monkeypatch):
    """Point the registry at a file this test controls."""

    def _write(payload) -> None:
        path = tmp_path / "registry.json"
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
        )
        monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(path))

    return _write


@pytest.fixture()
def slots_at(tmp_path, monkeypatch):
    def _write(payload) -> None:
        path = tmp_path / "slots.json"
        path.write_text(
            payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
        )
        monkeypatch.setenv(llm_registry.ENV_SLOT_CONFIG, str(path))

    return _write


# ---------------------------------------------------------------------------------------------
# The fail-closed contract. A configured allowlist that cannot be read must permit NOTHING.
# ---------------------------------------------------------------------------------------------


def test_a_configured_but_unreadable_slot_file_permits_nothing(tmp_path, monkeypatch):
    """The contract, stated in the module and never exercised.

    Falling back to defaults here would broaden execution at exactly the moment the operator's
    allowlist stopped being readable — the failure mode a fail-closed rule exists to prevent.
    """
    monkeypatch.setenv(llm_registry.ENV_SLOT_CONFIG, str(tmp_path / "absent.json"))
    assert llm_registry.load_slot_config() == []


def test_a_configured_but_malformed_slot_file_permits_nothing(slots_at):
    slots_at("{not json")
    assert llm_registry.load_slot_config() == []


def test_an_unconfigured_path_may_use_the_defaults(monkeypatch):
    """The other half of the same rule, and the reason it is not simply "always fail closed".

    With no allowlist configured there is nothing to narrow, so the built-in slots are the
    intended behaviour. Asserting both halves is what makes this a contract rather than a habit.
    """
    monkeypatch.delenv(llm_registry.ENV_SLOT_CONFIG, raising=False)
    assert llm_registry.load_slot_config() == llm_registry.default_slots()


def test_slots_that_are_not_a_list_are_refused(slots_at):
    """A mapping where a list belongs is a config error, not zero slots quietly."""
    slots_at({"slots": {"not": "a list"}})
    assert llm_registry.load_slot_config() == []


def test_one_bad_slot_entry_does_not_discard_the_good_ones(slots_at, caplog):
    """Dropping the whole file would fail closed on a typo; keeping the bad entry would admit it.

    Ignoring only the invalid entry — and SAYING so — is the behaviour that lets an operator find
    the typo without losing the rest of their allowlist.
    """
    slots_at({"slots": [{"name": "verify", "provider": "anthropic"}, "not-an-object"]})
    with caplog.at_level("WARNING"):
        slots = llm_registry.load_slot_config()
    assert len(slots) <= 1
    assert any("invalid slot entry" in record.message.lower() for record in caplog.records)


# ---------------------------------------------------------------------------------------------
# The model registry. A malformed entry must not become a usable model.
# ---------------------------------------------------------------------------------------------


def test_models_that_are_not_a_list_yield_no_entries(registry_at):
    registry_at({"models": "anthropic"})
    assert llm_registry.load_model_registry() == []


def test_non_object_registry_denies_selection_decisions_too(registry_at):
    """The shared object loader must fail closed for every registry reader."""
    registry_at([])
    assert llm_registry.load_selection_decisions() == []


def test_a_non_object_model_entry_is_skipped_and_logged(registry_at, caplog):
    registry_at({"models": [{"provider": "anthropic", "model_id": "claude-x"}, "oops"]})
    with caplog.at_level("WARNING"):
        entries = llm_registry.load_model_registry()
    assert [e.model for e in entries] == ["claude-x"]
    assert any("invalid model registry entry" in r.message.lower() for r in caplog.records)


@pytest.mark.parametrize(
    "entry",
    [
        {"provider": "", "model_id": "claude-x"},
        {"provider": "anthropic", "model_id": ""},
        {"provider": "anthropic"},
        {"model_id": "claude-x"},
        {},
    ],
)
def test_an_entry_missing_either_half_of_its_identity_is_dropped(registry_at, entry):
    """A provider without a model, or a model without a provider, cannot be executed.

    Admitting a half-identified entry would put a row in the registry that resolves to an empty
    model id — which reads downstream as "use the default" rather than as a broken config.
    """
    registry_at({"models": [entry]})
    assert llm_registry.load_model_registry() == []


def test_a_valid_entry_survives_beside_invalid_ones(registry_at):
    """The complement: the filtering must not be so eager that it empties a working registry."""
    registry_at(
        {
            "models": [
                {"provider": "", "model_id": "x"},
                {"provider": "anthropic", "model_id": "claude-x"},
                "junk",
            ]
        }
    )
    entries = llm_registry.load_model_registry()
    assert [(e.provider, e.model) for e in entries] == [("anthropic", "claude-x")]


# ---------------------------------------------------------------------------------------------
# Selection decisions.
# ---------------------------------------------------------------------------------------------


def test_selections_that_are_not_a_list_yield_nothing(registry_at):
    """The mapping here is a COMPLETE, otherwise-valid selection, and that is the point.

    Written first with a partial dict, which passed for the wrong reason: the entry was dropped
    downstream for having no provider, so wrapping a mapping in a list instead of refusing it left
    the test green. A break demo is what showed it. With a fully valid mapping, a wrongly-wrapped
    selection becomes a USABLE decision, so the guard is the only thing standing between a config
    typo and a model choice nobody wrote.
    """
    registry_at(
        {
            "selections": {
                "provider": "anthropic",
                "profile": "verifier-balanced",
                "model_id": "claude-x",
            }
        }
    )
    assert llm_registry.load_selection_decisions() == []


def test_a_non_object_selection_is_skipped(registry_at):
    registry_at(
        {
            "selections": [
                "junk",
                {"provider": "anthropic", "profile": "verifier-balanced", "model_id": "claude-x"},
            ]
        }
    )
    decisions = llm_registry.load_selection_decisions()
    assert len(decisions) == 1


def test_a_missing_registry_file_is_empty_not_an_exception(tmp_path, monkeypatch):
    """Callers treat an empty registry as "nothing configured"; an exception would abort the run."""
    monkeypatch.setenv(llm_registry.ENV_MODEL_REGISTRY_CONFIG, str(tmp_path / "absent.json"))
    assert llm_registry.load_model_registry() == []
    assert llm_registry.load_selection_decisions() == []


# --- Workflows#4367: overrides address configured positions; retirement is judged after overrides


def _clear_slot_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("LANGCHAIN_SLOT") or key == "LANGCHAIN_MODEL":
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(params=["canonical", "consumer-template", "trip-planner-1957-head-7ca6deb8"])
def slot_registry(request, monkeypatch, tmp_path):
    """Exercise provider validation in source, template, and the observed consumer head."""
    if request.param == "canonical":
        return llm_registry
    root = Path(__file__).resolve().parents[1]
    if request.param == "consumer-template":
        path = root / "templates/consumer-repo/tools/llm_registry.py"
    else:
        # Load the immutable delivered bytes as Python without altering the capture.
        # This tests actual slot behavior beyond its consumer-layout mypy result.
        path = tmp_path / "delivered_llm_registry.py"
        shutil.copy(root / "tests/fixtures/issue_4506/llm_registry.py.txt", path)
    spec = importlib.util.spec_from_file_location("consumer_slot_registry", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their defining module through sys.modules during import.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "provider_fields", [{}, {"provider": None}, {"provider": ""}, {"provider": "unknown"}]
)
@pytest.mark.parametrize(
    "history_provider_fields", [{}, {"provider": None}, {"provider": ""}, {"provider": "unknown"}]
)
@pytest.mark.parametrize(
    "override_position, provider_only",
    [(None, False), (1, False), (2, False), (2, True), (3, False)],
    ids=["no-override", "invalid-slot", "retired-slot", "retired-provider-only", "valid-slot"],
)
def test_a_missing_provider_cannot_become_a_retired_slot(
    registry_at,
    slots_at,
    monkeypatch,
    slot_registry,
    provider_fields,
    history_provider_fields,
    override_position,
    provider_only,
):
    """Reject missing providers without shifting numbered overrides onto other slots."""
    _clear_slot_env(monkeypatch)
    registry_at(
        {
            "models": [
                {"provider": "anthropic", "model_id": "claude-x", "lifecycle": "current"},
                {"provider": "anthropic", "model_id": "claude-y", "lifecycle": "current"},
            ],
            "selections": [
                {
                    "provider": "anthropic",
                    "model_id": "claude-y",
                    "profile": "verifier-balanced",
                    "status": "approved",
                    "evidence_ids": ["review-1"],
                }
            ],
            "selection_history": [
                {
                    "profile": "verifier-balanced",
                    "superseded_by": "retired",
                    **history_provider_fields,
                },
                {
                    "profile": "verifier-balanced",
                    "provider": "openai",
                    "superseded_by": "retired",
                },
            ],
        }
    )
    slots_at(
        {
            "slots": [
                {"name": "invalid", "model": "unusable", **provider_fields},
                {"name": "retired", "provider": "openai", "model": "old-model"},
                {"name": "valid", "provider": "anthropic", "model": "claude-x"},
            ]
        }
    )
    retired_slot = slot_registry.SlotDefinition(
        name="retired", provider="openai", model="old-model"
    )
    valid_slot = slot_registry.SlotDefinition(name="valid", provider="anthropic", model="claude-x")
    if override_position is not None and not provider_only:
        monkeypatch.setenv(f"LANGCHAIN_SLOT{override_position}_MODEL", "claude-y")
    if override_position == 2:
        monkeypatch.setenv("LANGCHAIN_SLOT2_PROVIDER", "anthropic")

    assert slot_registry._load_positional_slots() == [
        (2, "verifier-balanced", retired_slot, True),
        (3, "verifier-balanced", valid_slot, False),
    ]
    assert slot_registry.load_slot_config() == [valid_slot]
    expected_slot = (
        slot_registry.SlotDefinition(name="valid", provider="anthropic", model="claude-y")
        if override_position == 3
        else valid_slot
    )
    expected_slots = [expected_slot]
    if override_position == 2:
        # The provider guard must retain valid retired placeholders so an override
        # can replace them, even when a preceding invalid slot was discarded.
        # Without a model override, use the new provider's reviewed selection.
        expected_slots.insert(
            0,
            slot_registry.SlotDefinition(name="retired", provider="anthropic", model="claude-y"),
        )
    assert slot_registry.resolve_slots() == expected_slots


@pytest.mark.parametrize(
    "provider_fields", [{}, {"provider": None}, {"provider": ""}, {"provider": "unknown"}]
)
@pytest.mark.parametrize("override", [False, True], ids=["no-override", "model-override"])
@pytest.mark.parametrize("retired_history", [False, True], ids=["no-history", "invalid-history"])
def test_an_allowlist_with_only_a_missing_provider_remains_empty(
    registry_at, slots_at, monkeypatch, slot_registry, provider_fields, override, retired_history
):
    """An invalid identity cannot enable defaults or acquire an identity via overrides."""
    _clear_slot_env(monkeypatch)
    registry_at(
        {
            "models": [{"provider": "anthropic", "model_id": "claude-x", "lifecycle": "current"}],
            "selections": [
                {
                    "provider": "anthropic",
                    "model_id": "claude-x",
                    "profile": "verifier-balanced",
                    "status": "approved",
                    "evidence_ids": ["review-1"],
                }
            ],
            "selection_history": (
                [{"profile": "verifier-balanced", "superseded_by": "retired", **provider_fields}]
                if retired_history
                else []
            ),
        }
    )
    # Make the fail-closed assertion meaningful: a reviewed default is available,
    # but an explicit invalid allowlist must not enable it.
    assert (
        slot_registry.SlotDefinition(name="slot2", provider="anthropic", model="claude-x")
        in slot_registry.default_slots()
    )
    slots_at({"slots": [{"name": "invalid", "model": "claude-x", **provider_fields}]})
    if override:
        monkeypatch.setenv("LANGCHAIN_MODEL", "claude-x")
        monkeypatch.setenv("LANGCHAIN_SLOT1_PROVIDER", "anthropic")
        monkeypatch.setenv("LANGCHAIN_SLOT1_MODEL", "claude-x")

    # A malformed retirement record must not turn the missing provider into a
    # placeholder that an environment override can revive.
    assert slot_registry._load_positional_slots() == []
    assert slot_registry.load_slot_config() == []
    assert slot_registry.resolve_slots() == []
    assert slot_registry.configured_model_for_provider("anthropic", fallback="claude-x") == ""


def test_a_missing_provider_with_a_reviewed_profile_preserves_valid_slots(
    registry_at, slots_at, monkeypatch, slot_registry
):
    """A reviewed profile supplies a model only after the slot identifies its provider."""
    _clear_slot_env(monkeypatch)
    profile = "explicit-review"
    registry_at(
        {
            "models": [{"provider": "anthropic", "model_id": "claude-x", "lifecycle": "current"}],
            "selections": [
                {
                    "provider": "anthropic",
                    "model_id": "claude-x",
                    "profile": profile,
                    "status": "approved",
                    "evidence_ids": ["review-1"],
                }
            ],
            "selection_history": [{"profile": profile, "superseded_by": "retired"}],
        }
    )
    slots_at(
        {
            "slots": [
                {"name": "invalid", "profile": profile},
                {"name": "reviewed", "provider": "anthropic", "profile": profile},
            ]
        }
    )
    # A provider-less retirement key must never create a provider-less placeholder,
    # even though this profile has a valid reviewed model for another slot.
    valid_slot = slot_registry.SlotDefinition(
        name="reviewed", provider="anthropic", model="claude-x"
    )
    assert slot_registry._load_positional_slots() == [(2, profile, valid_slot, False)]
    assert slot_registry.load_slot_config() == [valid_slot]
    assert slot_registry.resolve_slots() == [valid_slot]


def test_a_skipped_retired_slot_does_not_shift_numbered_overrides(slots_at, monkeypatch):
    _clear_slot_env(monkeypatch)
    slots_at(
        {
            "slots": [
                {"name": "slot1", "provider": "github-models", "model": "openai/gpt-5"},
                {"name": "slot2", "provider": "openai"},
                {"name": "slot3", "provider": "anthropic"},
            ]
        }
    )
    anthropic = llm_registry.select_model_for_profile(provider="anthropic")
    # The operator overrides slot 2 (openai); before the fix it landed on anthropic,
    # because the retired slot 1 had been dropped before numbering.
    monkeypatch.setenv("LANGCHAIN_SLOT2_MODEL", "gpt-6.1-terra")
    resolved = llm_registry.resolve_slots()
    assert [(s.name, s.provider) for s in resolved] == [("slot2", "openai"), ("slot3", "anthropic")]
    assert resolved[0].model == "gpt-6.1-terra"
    assert resolved[1].model == anthropic
    # load_slot_config keeps its contract: usable slots only, retired one excluded
    assert [s.provider for s in llm_registry.load_slot_config()] == ["openai", "anthropic"]


def test_an_override_cannot_reintroduce_a_retired_selection(slots_at, monkeypatch):
    _clear_slot_env(monkeypatch)
    slots_at(
        {
            "slots": [
                {"name": "slot1", "provider": "openai"},
                {"name": "slot2", "provider": "anthropic"},
            ]
        }
    )
    monkeypatch.setenv("LANGCHAIN_SLOT1_PROVIDER", "github-models")
    monkeypatch.setenv("LANGCHAIN_SLOT1_MODEL", "openai/gpt-5")
    resolved = llm_registry.resolve_slots()
    assert "github-models" not in [s.provider for s in resolved]
    assert llm_registry.configured_model_for_provider("github-models") == ""


def test_an_override_may_replace_a_retired_slot_with_a_current_selection(slots_at, monkeypatch):
    _clear_slot_env(monkeypatch)
    slots_at(
        {
            "slots": [
                {"name": "slot1", "provider": "github-models"},
                {"name": "slot2", "provider": "anthropic"},
            ]
        }
    )
    monkeypatch.setenv("LANGCHAIN_SLOT1_PROVIDER", "openai")
    monkeypatch.setenv("LANGCHAIN_SLOT1_MODEL", "gpt-6.1-sol")
    resolved = llm_registry.resolve_slots()
    assert [(s.name, s.provider, s.model) for s in resolved][0] == (
        "slot1",
        "openai",
        "gpt-6.1-sol",
    )


def test_a_provider_only_override_on_a_retired_slot_takes_the_reviewed_model(slots_at, monkeypatch):
    _clear_slot_env(monkeypatch)
    slots_at(
        {
            "slots": [
                {"name": "slot1", "provider": "github-models", "model": "openai/gpt-5"},
                {"name": "slot2", "provider": "anthropic"},
            ]
        }
    )
    monkeypatch.setenv("LANGCHAIN_SLOT1_PROVIDER", "openai")
    resolved = llm_registry.resolve_slots()
    reviewed = llm_registry.select_model_for_profile(provider="openai")
    assert (resolved[0].name, resolved[0].provider, resolved[0].model) == (
        "slot1",
        "openai",
        reviewed,
    )
    assert resolved[0].model != "openai/gpt-5"
