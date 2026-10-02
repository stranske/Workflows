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
    pytest.param(11, 75_300, 3_200, True, id="manager-database-1703-shape"),
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
        assert coverage.code_ratio < pr_verifier.MIN_CODE_COVERAGE_RATIO
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


def test_free_form_context_without_declared_sections_is_unchanged() -> None:
    coverage = pr_verifier.prompt_coverage("short ad-hoc context", None)
    assert coverage.sufficient
    assert coverage.acceptance == "not_declared"
    assert coverage.code == "not_declared"
