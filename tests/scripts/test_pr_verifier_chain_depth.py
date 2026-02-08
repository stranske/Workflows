"""Tests for chain depth awareness in pr_verifier."""

from __future__ import annotations

import textwrap

from scripts.langchain.pr_verifier import (
    CHAIN_DEPTH_ADDENDUM,
    _get_chain_depth,
    _prepare_prompt,
)


class TestGetChainDepth:
    """Unit tests for _get_chain_depth()."""

    def test_default_zero(self, monkeypatch):
        monkeypatch.delenv("CHAIN_DEPTH", raising=False)
        assert _get_chain_depth() == 0

    def test_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "3")
        assert _get_chain_depth() == 3

    def test_zero_value(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "0")
        assert _get_chain_depth() == 0

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "-1")
        assert _get_chain_depth() == 0

    def test_invalid_returns_zero(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "not-a-number")
        assert _get_chain_depth() == 0

    def test_empty_returns_zero(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "")
        assert _get_chain_depth() == 0


class TestChainDepthAddendum:
    """Test that chain depth addendum is included in prompts for follow-ups."""

    def test_addendum_contains_depth_placeholder(self):
        formatted = CHAIN_DEPTH_ADDENDUM.format(depth=2)
        assert "follow-up iteration 2" in formatted
        assert "chain depth 2" in formatted.lower()

    def test_no_addendum_at_depth_zero(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "0")
        prompt = _prepare_prompt("test context", None)
        assert "Follow-up Iteration Context" not in prompt

    def test_addendum_at_depth_one(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "1")
        prompt = _prepare_prompt("test context", None)
        assert "Follow-up Iteration Context" in prompt
        assert "follow-up iteration 1" in prompt

    def test_addendum_at_depth_three(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "3")
        prompt = _prepare_prompt("test context", None)
        assert "follow-up iteration 3" in prompt

    def test_addendum_deprioritizes_testing(self, monkeypatch):
        monkeypatch.setenv("CHAIN_DEPTH", "2")
        prompt = _prepare_prompt("test context", None)
        # The addendum should tell the LLM not to raise CONCERNS for tests alone
        assert "testing" in prompt.lower()
        assert "CONCERNS solely for missing" in prompt

    def test_addendum_combined_with_infra(self, monkeypatch):
        """Chain depth addendum should stack with infra addendum."""
        monkeypatch.setenv("CHAIN_DEPTH", "2")
        infra_diff = textwrap.dedent(
            """\
            diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
            --- a/.github/workflows/ci.yml
            +++ b/.github/workflows/ci.yml
            @@ -1,3 +1,3 @@
            -old
            +new
            diff --git a/scripts/deploy.sh b/scripts/deploy.sh
            --- a/scripts/deploy.sh
            +++ b/scripts/deploy.sh
            @@ -1,3 +1,3 @@
            -old
            +new
        """
        )
        prompt = _prepare_prompt("test context", infra_diff)
        # Both addenda should be present
        assert "Infrastructure Change Guidance" in prompt or "infrastructure" in prompt.lower()
        assert "Follow-up Iteration Context" in prompt

    def test_no_addendum_without_env(self, monkeypatch):
        monkeypatch.delenv("CHAIN_DEPTH", raising=False)
        prompt = _prepare_prompt("test context", None)
        assert "Follow-up Iteration Context" not in prompt


class TestVerdictGuidelines:
    """Test that verdict guidelines are present in the standard prompt."""

    def test_standard_prompt_has_verdict_guidelines(self, monkeypatch):
        monkeypatch.delenv("CHAIN_DEPTH", raising=False)
        prompt = _prepare_prompt("test context", None)
        assert "Verdict Guidelines" in prompt
        assert "Testing gaps alone" in prompt

    def test_pass_not_blocked_by_testing_alone(self, monkeypatch):
        monkeypatch.delenv("CHAIN_DEPTH", raising=False)
        prompt = _prepare_prompt("test context", None)
        assert "should NOT prevent a PASS" in prompt
