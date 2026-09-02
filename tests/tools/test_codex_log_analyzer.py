"""Tests for tools/codex_log_analyzer.py."""

from tools.codex_log_analyzer import (
    _build_summary,
    _build_test_module_map,
    _expand_synonyms,
    _extract_file_refs,
    _extract_tasks_from_markdown,
    _first_matching_file,
    _has_exact_file_match,
    _has_test_module_match,
    _match_tasks_to_evidence,
    _split_camel_case,
    analyze_codex_log,
)


def test_extract_tasks_ignores_details_summary_tags() -> None:
    markdown = """
- [ ] <details>
- [ ] <summary>What should I do?</summary>
- [ ] Actual task
- [x] Completed task
- [ ] </details>
"""
    tasks = _extract_tasks_from_markdown(markdown, include_checked=False)
    assert tasks == ["Actual task"]


def test_extract_tasks_keeps_completed_but_skips_tags() -> None:
    markdown = """
- [ ] <details>
- [ ] Actual task
- [x] Completed task
- [ ] </details>
"""
    tasks = _extract_tasks_from_markdown(markdown, include_checked=True)
    assert tasks == ["Actual task", "Completed task"]


# ---------------------------------------------------------------------------
# The confidence-scoring engine below (_match_tasks_to_evidence and its
# helpers) had no test coverage at all beyond the markdown-extraction tests
# above. It is a pure, self-contained heuristic -- no I/O, no side effects --
# so every property below is pinned by calling the real functions with
# concrete inputs and asserting on their exact, hand-verified output.
# ---------------------------------------------------------------------------


def test_expand_synonyms_adds_configured_alternatives() -> None:
    """A keyword present in SYNONYMS gains its configured alternatives."""
    expanded = _expand_synonyms({"remove"})
    assert expanded == {"remove", "delete", "drop", "eliminate"}


def test_expand_synonyms_leaves_unmapped_keyword_untouched() -> None:
    """A keyword with no SYNONYMS entry passes through unchanged."""
    expanded = _expand_synonyms({"zzz_not_a_key"})
    assert expanded == {"zzz_not_a_key"}


def test_split_camel_case_splits_acronym_and_titlecase_boundaries() -> None:
    """Both camelCase and ACRONYM+Titlecase boundaries are split."""
    assert _split_camel_case("HTTPServerConfig") == ["http", "server", "config"]
    assert _split_camel_case("authToken") == ["auth", "token"]


def test_split_camel_case_drops_short_fragments() -> None:
    """Fragments of length <= 2 are dropped as too short to be meaningful keywords."""
    assert _split_camel_case("ID") == []


def test_build_test_module_map_adds_plural_form_for_singular_module() -> None:
    """A module name not already ending in 's' gains a pluralized alias too."""
    module_map = _build_test_module_map(["tests/test_cache.py"])
    assert module_map == {"tests/test_cache.py": ["cache", "caches", "cache"]}


def test_build_test_module_map_adds_singular_form_for_plural_module() -> None:
    """A module name already ending in 's' gains a singularized alias too."""
    module_map = _build_test_module_map(["tests/test_users.py"])
    assert module_map == {"tests/test_users.py": ["users", "user", "users"]}


def test_extract_file_refs_backtick_accepts_any_extension() -> None:
    """Backtick-quoted references accept any extension, not just code files."""
    assert _extract_file_refs("see `notes.txt` for detail") == ["notes.txt"]


def test_extract_file_refs_bare_reference_requires_known_extension() -> None:
    """A bare (non-backtick) reference is only recognized for known code extensions.

    This is an asymmetry worth pinning: the same reference to a .txt file is
    silently ignored without backticks, while a .py reference is recognized
    either way.
    """
    assert _extract_file_refs("see notes.txt for detail") == []
    assert _extract_file_refs("see src/app.py for detail") == ["src/app.py"]


def test_has_exact_file_match_matches_by_basename_across_directories() -> None:
    """A bare filename reference matches a changed file in any directory."""
    assert _has_exact_file_match(["auth.py"], ["src/deep/nested/auth.py"]) is True
    assert _has_exact_file_match(["auth.py"], ["src/other.py"]) is False


def test_first_matching_file_suffix_check_requires_path_boundary() -> None:
    """The selector rejects bare suffixes while keeping valid nested paths."""
    assert _first_matching_file(["test.py"], ["src/subtest.py"]) is None
    matched = _first_matching_file(["auth.py"], ["src/deep/nested/auth.py"])
    assert matched == "src/deep/nested/auth.py"
    assert _first_matching_file(["src/auth.py"], ["src/auth.py"]) == "src/auth.py"


def test_has_exact_file_match_suffix_check_requires_path_boundary() -> None:
    """The boolean matcher must reject a bare suffix but retain exact paths."""
    assert _has_exact_file_match(["test.py"], ["src/subtest.py"]) is False
    assert _has_exact_file_match(["src/auth.py"], ["src/auth.py"]) is True


def test_build_summary_reports_no_changes_detected() -> None:
    """With no matches and no file changes, the summary says nothing changed."""
    assert _build_summary([], []) == "No changes detected in codex log"


def test_build_summary_reports_no_matches_with_files_changed() -> None:
    """With no matches but files did change, the summary is explicitly different
    from the no-changes-at-all case -- files moved, but none looked task-related."""
    assert _build_summary([], ["src/app.py"]) == "No clear task matches found in codex log changes"


def test_build_summary_counts_high_and_medium_confidence() -> None:
    """The summary tallies high- and medium-confidence matches separately.

    Deliberately asymmetric (2 high, 1 medium): an earlier 1-high/1-medium
    version of this fixture failed to notice the two counters swapped, since
    swapping "1 high" for "1 medium" prints an identical string. An
    asymmetric mix makes the two counts distinguishable from each other.
    """
    matches = (
        _match_tasks_to_evidence(
            ["Rename the exported helper function inside `utils.py`"],
            ["src/utils.py"],
            [],
        )
        + _match_tasks_to_evidence(
            ["Add unit tests for cache module"],
            ["tests/test_cache.py"],
            [],
        )
        + _match_tasks_to_evidence(
            ["Investigate the billing integration flow for edge cases"],
            ["src/billing_gateway.py"],
            [],
        )
    )
    assert [m.confidence for m in matches] == ["high", "high", "medium"]
    assert _build_summary(matches, ["src/utils.py"]) == (
        "Found 3 potential task completion(s): 2 high, 1 medium confidence"
    )


def test_match_tasks_exact_file_match_wins_regardless_of_score() -> None:
    """An exact file reference yields 'high' via its own branch, not the score.

    Evidence is spread across three unrelated files so the keyword score stays
    low; only the exact backtick reference to `utils.py` should drive the
    result, which is verified by asserting the specific 'Exact file
    created/modified' reason text rather than just the confidence level.
    """
    files_changed = ["src/utils.py", "docs/readme.md", "config/settings.yaml"]
    task = "Rename the exported helper function inside `utils.py`"

    matches = _match_tasks_to_evidence([task], files_changed, [])

    assert len(matches) == 1
    assert matches[0].confidence == "high"
    assert matches[0].reason == "Exact file created/modified: src/utils.py"
    assert matches[0].evidence_files == ["src/utils.py"]


def test_match_tasks_high_confidence_via_keyword_score_and_file_evidence() -> None:
    """A high keyword-overlap score (>= 35%) combined with file evidence is 'high'.

    No file extension is referenced in the task text, so this exercises the
    score-driven branch specifically, not the exact-file-match branch.
    """
    files_changed = ["src/payment_processor.py"]
    commands = ["pytest tests/test_payment.py -v"]
    task = "Implement payment processor validation and add tests"

    matches = _match_tasks_to_evidence([task], files_changed, commands)

    assert len(matches) == 1
    assert matches[0].confidence == "high"
    assert matches[0].reason == "43% keyword match, evidence in files/commands"


def test_match_tasks_high_confidence_at_lower_score_threshold_with_file_match() -> None:
    """A 25-34% keyword score is 'high' only when combined with file_match.

    This is a distinct decision boundary from the >= 35% branch above: with no
    command evidence, a moderate score needs the file_match disjunct to reach
    'high' rather than 'medium', pinned via the specific reason text.
    """
    files_changed = ["src/inventory_sync.py"]
    task = "Fix inventory sync retry logic for warehouse updates"

    matches = _match_tasks_to_evidence([task], files_changed, [])

    assert len(matches) == 1
    assert matches[0].confidence == "high"
    assert matches[0].reason == "25% keyword match with file match"


def test_match_tasks_medium_confidence_via_bare_file_touch_despite_low_score() -> None:
    """A merely-touched file grants 'medium' even when the keyword score is low.

    The score here (1/8 = 12%) is below every 'high' threshold, so only the
    bare `file_match` disjunct in `score >= 0.2 or file_match` can explain a
    non-dropped result.
    """
    files_changed = ["src/billing_gateway.py"]
    task = "Investigate the billing integration flow for edge cases"

    matches = _match_tasks_to_evidence([task], files_changed, [])

    assert len(matches) == 1
    assert matches[0].confidence == "medium"
    assert matches[0].reason == "12% keyword match, file touched"


def test_match_tasks_drops_tasks_with_no_evidence() -> None:
    """A task with zero keyword overlap and no file/command evidence is dropped.

    Silently omitting the task (rather than including it as 'low') is a real,
    checkable behavior of the caller-facing contract: `matches` only ever
    contains medium/high confidence entries.
    """
    matches = _match_tasks_to_evidence(
        ["Investigate slow queries in the reporting dashboard"],
        [],
        [],
    )
    assert matches == []


def test_match_tasks_test_task_matches_module_reference_phrasing() -> None:
    """A test-authoring task naming its module via 'for X module' is 'high'.

    This is a distinct branch from keyword scoring: it fires from
    `is_test_task and test_module_match` alone, verified by the specific
    'Test file created matching module reference' reason.
    """
    matches = _match_tasks_to_evidence(
        ["Add unit tests for cache module"],
        ["tests/test_cache.py"],
        [],
    )

    assert len(matches) == 1
    assert matches[0].confidence == "high"
    assert matches[0].reason == "Test file created matching module reference"


def test_has_test_module_match_requires_word_directly_before_module() -> None:
    """The 'for X module' phrasing requires X to sit directly before 'module'.

    A determiner in between ('for the cache module') does not match -- the
    regex captures a single token, not a phrase. A backtick-quoted module
    name matches regardless of surrounding words.
    """
    module_map = _build_test_module_map(["tests/test_cache.py"])

    assert _has_test_module_match("add unit tests for cache module", module_map) is True
    assert _has_test_module_match("add unit tests for the cache module", module_map) is False
    assert _has_test_module_match("add unit tests for `cache`", module_map) is True


def test_analyze_codex_log_end_to_end_exact_match_and_summary() -> None:
    """The public entrypoint wires parsing, matching, and summarizing together."""
    jsonl = "\n".join(
        [
            '{"type": "item.completed", "item_type": "file_change", '
            '"path": "src/auth.py", "change_type": "modified"}',
            '{"type": "item.completed", "item_type": "command_execution", '
            '"command": "pytest tests/test_auth.py", "exit_code": 0}',
        ]
    )

    result = analyze_codex_log(jsonl, ["Fix `auth.py` login bug", "Update the README"])

    assert len(result.matches) == 1
    assert result.matches[0].task == "Fix `auth.py` login bug"
    assert result.matches[0].confidence == "high"
    assert result.matches[0].reason == "Exact file created/modified: src/auth.py"
    assert result.summary == "Found 1 potential task completion(s): 1 high, 0 medium confidence"
    assert result.session is not None


def test_analyze_codex_log_accepts_raw_markdown_checklist() -> None:
    """The public entrypoint also accepts a raw markdown checklist for `tasks`,
    routing it through `_extract_tasks_from_markdown` rather than a pre-split list."""
    jsonl = (
        '{"type": "item.completed", "item_type": "file_change", '
        '"path": "src/auth.py", "change_type": "modified"}'
    )
    markdown = "- [ ] Fix `auth.py` login bug\n- [x] Update the README\n"

    result = analyze_codex_log(jsonl, markdown, include_checked=False)

    # The checked "Update the README" item is excluded by include_checked=False.
    assert [m.task for m in result.matches] == ["Fix `auth.py` login bug"]
