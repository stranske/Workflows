"""Grammar patterns stay compiled when the stdlib regex cache is evicted."""

from scripts.langchain import pr_verifier


def test_large_grammar_patterns_survive_stdlib_regex_cache_eviction(monkeypatch):
    proxy = pr_verifier.re
    assert isinstance(proxy, pr_verifier._GrammarRegex)
    text = (
        "The UI must record evidence in the PR body settings panel that may "
        "contain command output and in a PR comment"
    )
    pr_verifier._cached_evidence_channels.cache_clear()
    pr_verifier._cached_evidence_options.cache_clear()
    channels = pr_verifier._required_evidence_channels(text)
    options = pr_verifier._required_evidence_options(text)
    assert any(len(pattern) >= proxy._LARGE_PATTERN_CHARS for pattern, _flags in proxy._patterns)

    for index in range(600):
        pr_verifier._stdlib_re.compile(rf"thrash-{index}-\d+")
    pr_verifier._cached_evidence_channels.cache_clear()
    pr_verifier._cached_evidence_options.cache_clear()

    compiled: list[int] = []
    real_compile = proxy._compile

    def spy(pattern, flags=0):
        if isinstance(pattern, str) and len(pattern) >= proxy._LARGE_PATTERN_CHARS:
            compiled.append(len(pattern))
        return real_compile(pattern, flags)

    monkeypatch.setattr(proxy, "_compile", spy)
    assert pr_verifier._required_evidence_channels(text) == channels
    assert pr_verifier._required_evidence_options(text) == options
    assert compiled == []
