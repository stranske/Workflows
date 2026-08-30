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

import json

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
