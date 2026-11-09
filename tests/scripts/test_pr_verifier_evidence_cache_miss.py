"""Cache-miss behavior for the evidence-channel and evidence-option lookups.

An empty classification is a stored result. The second call must be a hit.
A lookup that returned nothing is not the same event as a key that was never
stored, so the cache must not treat the empty result as a miss.
"""

from __future__ import annotations

from collections import Counter

from scripts.langchain import pr_verifier as verifier

EMPTY_CRITERION = "Tests pass; the reviewer must record it in an artifact"
BODY_CRITERION = "Evidence must be posted in the PR body"


def test_classifiers_share_bounded_immutable_normalization(monkeypatch) -> None:
    original = verifier._normalize_capability_deliveries
    calls = Counter()

    def observed(text):
        calls[text] += 1
        return original(text)

    monkeypatch.setattr(verifier, "_normalize_capability_deliveries", observed)
    cache = verifier._cached_evidence_normalization
    cache.cache_clear()
    verifier._cached_evidence_channels.cache_clear()
    verifier._cached_evidence_options.cache_clear()
    assert verifier._required_evidence_channels(BODY_CRITERION) == {"body"}
    assert verifier._required_evidence_options(BODY_CRITERION) == [{"body"}]
    assert calls[BODY_CRITERION] == 1
    assert cache.cache_info().maxsize == 512

    large = " " * (verifier._EVIDENCE_CACHE_MAX_CHARS + 1)
    before = cache.cache_info().currsize
    assert verifier._normalize_evidence_acceptance(large) == large
    assert verifier._normalize_evidence_acceptance(large) == large
    assert calls[large] == 2
    assert cache.cache_info().currsize == before

    monkeypatch.setattr(
        verifier, "_normalize_capability_deliveries", lambda text: text.replace("body", "comment")
    )
    assert "comment" in verifier._normalize_evidence_acceptance(BODY_CRITERION)


def test_empty_evidence_channel_result_is_a_cache_hit() -> None:
    channels = verifier._cached_evidence_channels
    channels.cache_clear()
    before = channels.cache_info()

    assert verifier._required_evidence_channels(EMPTY_CRITERION) == set()
    missed = channels.cache_info()
    assert missed.misses == before.misses + 1
    assert missed.hits == before.hits

    assert verifier._required_evidence_channels(EMPTY_CRITERION) == set()
    again = channels.cache_info()
    assert again.misses == missed.misses
    assert again.hits == missed.hits + 1

    assert verifier._required_evidence_channels(BODY_CRITERION) == {"body"}
    assert verifier._required_evidence_channels(EMPTY_CRITERION) == set()


def test_empty_evidence_option_result_is_a_cache_hit() -> None:
    options = verifier._cached_evidence_options
    options.cache_clear()
    before = options.cache_info()

    assert verifier._required_evidence_options(EMPTY_CRITERION) == [set()]
    missed = options.cache_info()
    assert missed.misses == before.misses + 1
    assert missed.hits == before.hits

    assert verifier._required_evidence_options(EMPTY_CRITERION) == [set()]
    again = options.cache_info()
    assert again.misses == missed.misses
    assert again.hits == missed.hits + 1

    assert verifier._required_evidence_options(BODY_CRITERION) == [{"body"}]
    assert verifier._required_evidence_options(EMPTY_CRITERION) == [set()]
