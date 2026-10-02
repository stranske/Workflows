"""The verifier prompt must state its own coverage and never PASS on omitted code (#3701)."""

from __future__ import annotations

import json
from unittest import mock

import pytest
from scripts.langchain import pr_verifier

ACCEPTANCE_SENTINEL = "ACCEPTANCE-SENTINEL: every changed module is wired"


def _file_diff(path: str, chars: int) -> str:
    header = f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,999 @@\n"
    lines = []
    size = len(header)
    index = 0
    while size < chars:
        line = f"+{path.replace('/', '_').replace('.', '_')}_line_{index} = {index}\n"
        lines.append(line)
        size += len(line)
        index += 1
    return header + "".join(lines)


def _context(
    files: int,
    code_chars: int,
    acceptance_chars: int,
    *,
    ci_chars: int = 900,
    drop_acceptance: bool = False,
    drop_diff: bool = False,
    drop_file: int | None = None,
) -> tuple[str, list[str]]:
    """Production-shaped verifier-context.md, as agents_verifier_context.js writes it."""
    paths = [f"src/pkg_{index}/module_{index}.py" for index in range(files)]
    # Uneven sizes, like a real PR: a few large files and many small ones.
    weights = [1 + (index % 4) * 3 for index in range(files)]
    total_weight = sum(weights)
    diffs = [
        _file_diff(path, code_chars * w // total_weight)
        for path, w in zip(paths, weights, strict=True)
    ]
    plan_body = (
        "### Pull request #1: change\n\n"
        + ("- [x] scoped task detail\n" * 400)[: max(0, acceptance_chars - 200)]
    )
    plan = (
        "## Plan sources (scope, tasks, acceptance)\n\n"
        + plan_body
        + "\n## Context for Agent\n\n#### Acceptance criteria\n- "
        + ACCEPTANCE_SENTINEL
        + "\n"
    )
    summary = (
        "## PR Diff Summary\n\n- Files changed: "
        + str(files)
        + "\n\n### File changes\n"
        + "".join(f"- {path} (+10/-0)\n" for path in paths)
    )
    shown = [diff for index, diff in enumerate(diffs) if index != drop_file]
    parts = [
        "# Verifier context\n\n- Repository: stranske/Example\n",
        "## CI Information\n\n| Workflow | Conclusion |\n"
        + ("| ci | success |\n" * (ci_chars // 16 + 1))[:ci_chars],
    ]
    if not drop_acceptance:
        parts.append(plan)
    parts.append(summary)
    if not drop_diff:
        parts.append("## PR Diff (full)\n\n```diff\n" + "".join(shown) + "```\n")
    return "\n".join(parts), paths


# File counts and code sizes of the three zero-API-call captures in MAINT-78 run
# 37018335161: Workflows #3601, Manager-Database #1703 and Pension-Data #912.
CAPTURED_SHAPES = [
    pytest.param(30, 159_700, 9_000, False, id="workflows-3601-shape"),
    # Every file is represented, but the 16k-token code budget still cuts
    # some lines. A representative excerpt cannot support PASS (#3701).
    pytest.param(11, 75_300, 3_200, False, id="manager-database-1703-shape"),
    pytest.param(9, 27_600, 1_500, True, id="pension-data-912-shape"),
]


@pytest.mark.parametrize(("files", "code_chars", "acceptance_chars", "sufficient"), CAPTURED_SHAPES)
def test_captured_shapes_state_coverage_and_reach_every_file(
    files: int, code_chars: int, acceptance_chars: int, sufficient: bool
) -> None:
    context, paths = _context(files, code_chars, acceptance_chars)
    assert len(context) > 8000  # the old per-block prefix cap

    prompt = pr_verifier._prepare_prompt(context, None)
    coverage = pr_verifier.prompt_coverage(context, None)

    assert "## Verifier input coverage" in prompt
    assert ACCEPTANCE_SENTINEL in prompt
    assert coverage.acceptance == "complete"
    # Every changed file is represented, including the last one, whose code
    # began far past the first 8,000 context characters.
    for path in paths:
        assert f"diff --git a/{path} b/{path}" in prompt
    last = paths[-1].replace("/", "_").replace(".", "_")
    assert f"+{last}_line_0 = 0" in prompt
    assert coverage.to_dict()["files_omitted"] == 0
    assert coverage.sufficient is sufficient
    if sufficient:
        assert "Coverage verdict: sufficient" in prompt
    else:
        assert coverage.code == "truncated"
        assert coverage.code_ratio < pr_verifier.MIN_CODE_COVERAGE_RATIO or any(
            reason.startswith("Changed code was truncated to fit the prompt budget")
            for reason in coverage.reasons
        )
        assert "INCOMPLETE — do not return PASS" in prompt


def _pass_client() -> mock.MagicMock:
    response = mock.MagicMock()
    response.content = json.dumps(
        {
            "verdict": "PASS",
            "confidence": 0.9,
            "scores": {
                "correctness": 9,
                "completeness": 9,
                "quality": 9,
                "testing": 9,
                "risks": 9,
            },
            "concerns": [],
            "summary": "Looks complete.",
        }
    )
    client = mock.MagicMock()
    client.invoke.return_value = response
    return client


@pytest.mark.parametrize(("files", "code_chars", "acceptance_chars", "sufficient"), CAPTURED_SHAPES)
def test_model_pass_is_withheld_when_most_code_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    files: int,
    code_chars: int,
    acceptance_chars: int,
    sufficient: bool,
) -> None:
    context, _ = _context(files, code_chars, acceptance_chars)
    client = _pass_client()
    monkeypatch.setattr(
        pr_verifier, "_get_llm_client", lambda model=None, provider=None: (client, "openai")
    )
    monkeypatch.setattr(pr_verifier, "_get_llm_clients", lambda m1=None, m2=None: [])

    result = pr_verifier.evaluate_pr(context)
    compare = pr_verifier.ComparisonRunner.from_environment(context, None).run_single(
        client, "openai", "model"
    )

    for verdict in (result, compare):
        assert verdict.input_coverage is not None
        assert verdict.input_coverage["sufficient"] is sufficient
        if sufficient:
            assert verdict.verdict == "PASS"
        else:
            assert verdict.verdict == "CONCERNS"
            assert verdict.concerns[0].startswith("Verifier input coverage incomplete")


@pytest.mark.parametrize(
    ("omission", "reason"),
    [
        ({"drop_acceptance": True}, "Acceptance/plan sources"),
        ({"drop_diff": True}, "Changed code is unavailable"),
        ({"drop_file": 3}, "listed in the diff summary are absent from the diff"),
    ],
)
def test_deliberate_omission_after_first_8000_chars_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch, omission: dict[str, object], reason: str
) -> None:
    # A long CI section pushes acceptance and code past the first 8,000 characters.
    control, _ = _context(4, 6_000, 1_200, ci_chars=9_000)
    assert control.index(ACCEPTANCE_SENTINEL) > 8000
    assert pr_verifier.prompt_coverage(control, None).sufficient

    context, _ = _context(4, 6_000, 1_200, ci_chars=9_000, **omission)  # type: ignore[arg-type]
    coverage = pr_verifier.prompt_coverage(context, None)
    assert not coverage.sufficient
    assert any(reason in item for item in coverage.reasons)

    client = _pass_client()
    monkeypatch.setattr(
        pr_verifier, "_get_llm_client", lambda model=None, provider=None: (client, "openai")
    )
    result = pr_verifier.evaluate_pr(context)
    assert result.verdict == "CONCERNS"
    assert reason in result.concerns[0]


def test_truncated_acceptance_is_reported_not_presented_as_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VERIFIER_CONTEXT_BUDGET_TOKENS", "500")
    context, _ = _context(3, 3_000, 6_000)
    coverage = pr_verifier.prompt_coverage(context, None)
    assert coverage.acceptance == "truncated"
    assert not coverage.sufficient


def test_free_form_context_without_diff_withholds_pass() -> None:
    coverage = pr_verifier.prompt_coverage("short ad-hoc context", None)
    assert not coverage.sufficient
    assert coverage.acceptance == "not_declared"
    assert coverage.code == "unavailable"
    assert any("Changed code is unavailable" in reason for reason in coverage.reasons)


def test_acceptance_evidence_has_its_own_budget_and_preserves_plan() -> None:
    context, _ = _context(1, 1_000, 1_000)
    context = context.replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n"
        "- Overall retrieval status: **present**\n\n"
        "### Bounded PR comments\n\n"
        + ("untrusted artifact detail\n" * 20_000)
        + "\n## PR Diff Summary",
    )

    coverage = pr_verifier.prompt_coverage(context, None)
    prompt = pr_verifier._prepare_prompt(context, None)

    assert coverage.acceptance == "complete"
    assert coverage.acceptance_evidence == "truncated"
    assert ACCEPTANCE_SENTINEL in prompt


def test_required_unavailable_acceptance_evidence_withholds_model_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(1, 1_000, 1_000)
    context = context.replace(
        ACCEPTANCE_SENTINEL,
        "required evidence artifact: a failing and restored passing transcript",
    ).replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n"
        "- Overall retrieval status: **unavailable**\n"
        "- PR comments: **unavailable** — API failure\n\n"
        "## PR Diff Summary",
    )
    coverage = pr_verifier.prompt_coverage(context, None)
    assert coverage.acceptance == "complete"
    assert coverage.acceptance_evidence == "complete"
    assert not coverage.sufficient
    assert any(
        "Required acceptance evidence is unavailable" in reason for reason in coverage.reasons
    )

    client = _pass_client()
    monkeypatch.setattr(
        pr_verifier, "_get_llm_client", lambda model=None, provider=None: (client, "openai")
    )
    result = pr_verifier.evaluate_pr(context)
    assert result.verdict == "CONCERNS"
    assert "Required acceptance evidence is unavailable" in result.concerns[0]


def test_late_required_evidence_omission_is_not_hidden_by_plan_budget() -> None:
    context, _ = _context(1, 1_000, 1_000, ci_chars=20_000)
    context = context.replace(
        ACCEPTANCE_SENTINEL,
        "required evidence artifact: exact test transcript",
    ).replace(
        "## PR Diff Summary",
        "## Acceptance evidence\n\n"
        "- Overall retrieval status: **unavailable**\n\n"
        "## PR Diff Summary",
    )
    assert context.index("## Acceptance evidence") > 8_000

    coverage = pr_verifier.prompt_coverage(context, None)

    assert coverage.acceptance == "complete"
    assert coverage.acceptance_evidence == "complete"
    assert not coverage.sufficient
    assert any(
        "Required acceptance evidence is unavailable" in reason for reason in coverage.reasons
    )


def test_summary_parser_covers_all_context_builder_file_forms() -> None:
    summary = """## PR Diff Summary

### File changes
- docs/modified file.md (+1/-2)
- src/added.py (added) (+10/-0)
- src/deleted.py (deleted) (+0/-8)
- old/name.py -> new/name.py (+2/-1)
- assets/logo.png (binary)
- ...and 3 more files
"""

    assert pr_verifier._summary_destination_paths(summary) == [
        "docs/modified file.md",
        "src/added.py",
        "src/deleted.py",
        "new/name.py",
        "assets/logo.png",
    ]


def test_summary_with_unquoted_spaces_and_rename_detects_missing_destination() -> None:
    context = """# Verifier context

## Plan sources (scope, tasks, acceptance)

#### Acceptance criteria
- exact observable smoke test

## PR Diff Summary

### File changes
- docs/modified file.md (+1/-0)
- old/name.py -> new/name.py (+2/-1)

## PR Diff (full)

```diff
diff --git a/docs/modified file.md b/docs/modified file.md
--- a/docs/modified file.md
+++ b/docs/modified file.md
@@ -1 +1 @@
-old
+new
```
"""

    coverage = pr_verifier.prompt_coverage(context, None)

    assert not coverage.sufficient
    assert coverage.files[0].path == "docs/modified file.md"
    assert any("new/name.py" in reason for reason in coverage.reasons)


def test_unquoted_apostrophe_path_is_preserved() -> None:
    context = """# Verifier context

## Plan sources (scope, tasks, acceptance)

#### Acceptance criteria
- exact observable smoke test

## PR Diff Summary

### File changes
- docs/owner's note.md (+1/-1)

## PR Diff (full)

```diff
diff --git a/docs/owner's note.md b/docs/owner's note.md
--- a/docs/owner's note.md
+++ b/docs/owner's note.md
@@ -1 +1 @@
-old
+new
```
"""

    coverage = pr_verifier.prompt_coverage(context, None)

    assert coverage.sufficient
    assert coverage.files[0].path == "docs/owner's note.md"


def test_complete_standalone_diff_ignores_truncated_embedded_copy() -> None:
    context, paths = _context(2, 2_000, 1_000)
    context = context.replace("```diff\n", "```diff\n...diff truncated after 1000 characters.\n", 1)
    standalone = "".join(_file_diff(path, 500) for path in paths)

    coverage = pr_verifier.prompt_coverage(context, standalone)

    assert coverage.sufficient
    assert coverage.code == "complete"
    assert not any("context builder truncated" in reason for reason in coverage.reasons)


def test_no_client_fallback_still_reports_input_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(2, 2_000, 1_000)
    monkeypatch.setattr(pr_verifier, "_get_llm_client", lambda model=None, provider=None: None)

    result = pr_verifier.evaluate_pr(context)

    assert result.used_llm is False
    assert result.input_coverage == pr_verifier.prompt_coverage(context, None).to_dict()


def test_invocation_fallback_still_reports_input_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _ = _context(2, 2_000, 1_000)
    client = mock.MagicMock()
    monkeypatch.setattr(
        pr_verifier, "_get_llm_client", lambda model=None, provider=None: (client, "openai")
    )
    monkeypatch.setattr(
        pr_verifier,
        "_invoke_llm",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    result = pr_verifier.evaluate_pr(context, provider="openai")

    assert result.used_llm is False
    assert result.input_coverage == pr_verifier.prompt_coverage(context, None).to_dict()


def test_comparison_invocation_fallback_still_reports_input_coverage() -> None:
    context, _ = _context(2, 2_000, 1_000)
    coverage = pr_verifier.prompt_coverage(context, None)
    runner = pr_verifier.ComparisonRunner(
        context=context,
        diff=None,
        prompt="prompt",
        clients=[],
        coverage=coverage,
    )

    with mock.patch.object(pr_verifier, "_invoke_llm", side_effect=RuntimeError("offline")):
        result = runner.run_single(mock.MagicMock(), "openai", "model")

    assert result.used_llm is False
    assert result.input_coverage == coverage.to_dict()
