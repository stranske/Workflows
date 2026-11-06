"""Cache-miss behavior for the evidence-channel and evidence-option lookups.

An empty classification is a stored result. The second call must be a hit.
A lookup that returned nothing is not the same event as a key that was never
stored, so the cache must not treat the empty result as a miss.
"""

from __future__ import annotations

from scripts.langchain import pr_verifier as verifier

EMPTY_CRITERION = "Tests pass; the reviewer must record it in an artifact"
BODY_CRITERION = "Evidence must be posted in the PR body"


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
